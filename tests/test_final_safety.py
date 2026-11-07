"""Cross-store recovery, document privacy and native route regressions."""
import os,json,hashlib,time,zipfile,uuid
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog,QPushButton,QScrollArea
from app.core.database import Database
from app.models.domain import Job,Photo,Layer
from app.services.cropping import CropTray
from app.services.documents import DocumentSession

@pytest.fixture
def app():return QApplication.instance() or QApplication([])

@pytest.fixture
def window(app,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user'))
    from app.ui.studio_window import StudioWindow
    w=StudioWindow();w.show();app.processEvents();yield w
    w.pool.waitForDone();app.processEvents();w.hardware.shutdown()
    for page in (w.shell.copy,w.shell.nid):page.dirty=False
    w.dirty=False;w.timer.stop();w.invalidate_autosave();w.close();app.processEvents()

def wait(w):
    end=time.monotonic()+15
    while w.busy and time.monotonic()<end:QApplication.processEvents();time.sleep(.005)
    assert not w.busy

@pytest.mark.parametrize('collision',['same_name','same_id','duplicate_name','duplicate_id','changed_payload'])
def test_recipe_bidirectional_collision_is_atomic(app,tmp_path,monkeypatch,collision):
    from app.ui.profiles import Profiles
    from app.services.profiles import normalize_profile
    db=Database(tmp_path/'studio.db');before=db.profiles();old=normalize_profile(before[0],validate=False)
    new=dict(old,name='New recipe',recipe_id=str(uuid.uuid4()));rows=[new]
    if collision=='same_name':rows.append(dict(old,recipe_id=str(uuid.uuid4())))
    if collision=='same_id':rows.append(dict(old,name='Other name'))
    if collision=='duplicate_name':rows.append(dict(new,recipe_id=str(uuid.uuid4())))
    if collision=='duplicate_id':rows.append(dict(new,name='Other new name'))
    if collision=='changed_payload':rows.append(dict(old,width=old['width']+1))
    path=tmp_path/'import.json';path.write_text(json.dumps(rows));errors=[]
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(str(path),''));monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a[-1]))
    widget=Profiles(db,lambda:None);widget.import_json();assert errors and db.profiles()==before;widget.close();db.conn.close()

def test_source_collision_never_replaces_existing_bytes(tmp_path):
    source=tmp_path/'scan.jpg';Image.new('RGB',(30,40)).save(source);original=source.read_bytes();digest=hashlib.sha256(original).hexdigest()
    tray=CropTray(root=tmp_path/'library');folder=tray.root/'sources';folder.mkdir(exist_ok=True);target=folder/(digest+'.jpg');target.write_bytes(b'preexisting user content')
    with pytest.raises(ValueError,match='different bytes'):tray.import_source(source)
    assert target.read_bytes()==b'preexisting user content' and source.read_bytes()==original and not tray.sources();tray.close()

def test_repaired_source_updates_job_snapshot_and_hidden_photos(window,tmp_path):
    w=window;source=tmp_path/'scan.jpg';Image.new('RGB',(30,40)).save(source);old=w.tray.import_source(source)
    item=w.tray.add('kept',Image.new('RGB',(20,30)),old);hidden=w.tray.add('removed',Image.new('RGB',(20,30)),old);w.tray.remove([hidden.id])
    job=Job(photos=[Photo(layers=[Layer(old)])]);w.db.save_job(job);Path(old).unlink();replacement=tmp_path/'scan.jpeg';replacement.write_bytes(source.read_bytes());new=w.tray.import_source(replacement)
    w.studio.customers.reconcile(w.tray)
    assert w.db.load_job(job.id).photos[0].layers[0].source==new
    assert w.tray.conn.execute('SELECT source FROM photos WHERE id=?',(hidden.id,)).fetchone()[0]==new
    assert w.tray.conn.execute('SELECT deleted FROM photos WHERE id=?',(hidden.id,)).fetchone()[0]==1
    assert w.tray.conn.execute('SELECT COUNT(*) FROM source_repairs').fetchone()[0]==0
    assert item.source==new and replacement.read_bytes()==source.read_bytes()

@pytest.mark.parametrize('missing',['source','removed','order'])
def test_backup_missing_required_assets_fails_before_output(window,tmp_path,missing):
    from app.services.storage import backup_data
    w=window;source=tmp_path/'original.png';Image.new('RGB',(30,40)).save(source);asset=w.tray.import_source(source);item=w.tray.add('photo',Image.new('RGB',(20,30)),asset)
    if missing=='source':Path(asset).unlink()
    elif missing=='removed':w.tray.remove([item.id]);Path(item.asset).unlink()
    else:
        w.db.save_job(Job(photos=[Photo(layers=[Layer(str(tmp_path/'missing.png'))])]))
    target=tmp_path/'existing.zip';target.write_bytes(b'preserve me')
    with pytest.raises(ValueError,match='missing|Missing'):backup_data(w.db.path.parent,target)
    assert target.read_bytes()==b'preserve me'

def test_transparent_document_is_white_and_unknown_dpi_requires_decision(tmp_path):
    source=tmp_path/'transparent.png';Image.new('RGBA',(300,400),(0,0,0,0)).save(source);before=source.read_bytes();session=DocumentSession(tmp_path);page=session.import_image(source)
    with pytest.raises(ValueError,match='DPI'):session.job({})
    path,_=session.prepared(page,{});assert Image.open(path).getpixel((100,100))==(255,255,255)
    assert session.job({'scale_mode':'fit'}).placements
    output=tmp_path/'processed.jpg';session.export_image(page,{'brightness':.5},output)
    assert Image.open(output).getpixel((100,100))[0]==pytest.approx(127,abs=2) and source.read_bytes()==before

def test_pdf_import_order_white_background_and_physical_size(app,tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    source=tmp_path/'input.pdf';pdf=Canvas(str(source),pagesize=(144,216));pdf.drawString(10,100,'Synthetic');pdf.showPage();pdf.setPageSize((216,144));pdf.drawString(10,100,'Second');pdf.save();before=source.read_bytes()
    session=DocumentSession(tmp_path);pages=session.import_pdf(source);assert len(pages)==2
    path,size=session.prepared(pages[0],{});assert Image.open(path).getpixel((0,0))==(255,255,255)
    job=session.job({});assert job.photos[0].width==pytest.approx(50.8,abs=.01) and job.photos[1].width==pytest.approx(76.2,abs=.01)
    assert source.read_bytes()==before

def test_nid_scan_callback_proposes_crop_without_library_rows(window,tmp_path,monkeypatch):
    w=window;workspace=w.shell.nid;w.stack.setCurrentWidget(workspace);scanner=w.hardware.scan_dialog
    monkeypatch.setattr(scanner,'scan_now',lambda:None);before=len(w.tray.items)
    for side in ('Front','Back'):
        workspace.scan(side);folder=workspace.session.root/(side+'.png');im=Image.new('RGB',(1000,700),'white')
        from PIL import ImageDraw
        draw=ImageDraw.Draw(im);draw.rectangle((80,100,900,610),fill='lightblue',outline='black',width=4);draw.text((200,300),'FICTIONAL SAMPLE',fill='black');im.save(folder)
        callback=scanner.completion_callback;scanner.completion_callback=None;callback(dict(original=str(folder),driver={'dpi':300}));wait(w);wait(w)
        assert workspace.current().points;workspace.confirm_crop();wait(w)
    assert len(w.tray.items)==before and len(workspace.make_job().placements)==2
    originals={p.source:Path(p.source).read_bytes() for p in workspace.session.pages};workspace.swap();wait(w);workspace.rotate();wait(w)
    assert all(Path(path).read_bytes()==data for path,data in originals.items())

def test_pending_scan_cancel_never_starts_acquisition(window,monkeypatch):
    hub=window.hardware;dialog=hub.scan_dialog;hub.scanners=[dict(id='scanner',name='Synthetic',backend='wia')];dialog.update_devices();calls=[]
    monkeypatch.setattr(hub.scan_process,'start',lambda *args:calls.append(args));dialog.scan_now();dialog.cancel()
    dialog.result('capabilities',dict(sources=[dict(id='bed',name='Bed',width_mm=210,height_mm=297,resolutions=[300],colors=['color'])],status='Ready'))
    assert not any(c[1]['action']=='scan' for c in calls) and not dialog.pending_scan

def test_tools_actual_control_bounds_and_gallery_height(window,app):
    w=window;w.resize(1050,740);w.studio.show(w.studio.tools);app.processEvents();tools=w.studio.tools
    assert tools.gallery.height()>=240
    content=tools.tabs.widget(0).widget();scroll=tools.tabs.widget(0);assert content.height()>=scroll.viewport().height()
    buttons=content.findChildren(QPushButton)
    assert all(b.height()>=22 and b.width()>0 for b in buttons)
    # Every bottom action can be reached by scrolling, rather than being clipped.
    target=next(b for b in buttons if b.text()=='Add reviewed results to print session');scroll.ensureWidgetVisible(target);app.processEvents()
    point=target.mapTo(scroll.viewport(),target.rect().center());assert scroll.viewport().rect().contains(point)

def test_cleanup_retains_saved_active_and_referenced_sessions(tmp_path):
    from app.services.retention import cleanup_temporary
    source=tmp_path/'image.png';Image.new('RGB',(30,40)).save(source);root=tmp_path/'data';sessions=[DocumentSession(root) for _ in range(4)]
    for s in sessions:s.import_image(source);os.utime(s.root,(1,1))
    sessions[0].keep=True;sessions[0].manifest(force=True);os.utime(sessions[0].root,(1,1))
    assert cleanup_temporary(root,[sessions[1].pages[0].source],[sessions[2].root])==1
    assert all(s.root.exists() for s in sessions[:3]) and not sessions[3].root.exists() and source.exists()

def test_document_export_cannot_target_imported_original(window,tmp_path,monkeypatch):
    workspace=window.shell.copy;source=tmp_path/'original.png';Image.new('RGB',(30,40)).save(source);before=source.read_bytes();workspace.session.import_image(source);workspace.list.addItem('Page');workspace.list.setCurrentRow(0);wait(window)
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(source),''));workspace.export_image()
    assert source.read_bytes()==before and 'original' in workspace.message.text().lower()
