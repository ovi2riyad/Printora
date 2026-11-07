import copy
import hashlib
import json
import math
import time
from dataclasses import asdict
import pytest
from PIL import Image
from app.models.domain import Photo,Layer,Job
from app.services.selections import combine,selection_mask
from app.services.imaging import prepare_layer,render_photo
from app.services.layout import auto_layout,validate_layout,layout_capacity
from app.services.print_geometry import footprint

@pytest.fixture
def source(tmp_path):
    p=tmp_path/'original.png';im=Image.new('RGBA',(400,300),'red');im.paste('blue',(200,0,400,300));im.save(p);return p

@pytest.mark.parametrize('kind',['rectangle','ellipse','lasso','polygon','selection_brush'])
def test_selection_shapes_and_source_integrity(source,kind):
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    points=[[.2,.2],[.8,.2],[.8,.8],[.2,.8]] if kind in ('lasso','polygon') else [[.2,.2],[.8,.8]]
    expr=dict(kind=kind,points=points,radius=.08)
    mask=selection_mask(expr,(400,300));assert mask.getbbox();assert mask.getpixel((0,299))==0
    layer=Layer(str(source));layer.mask_strokes=[dict(kind='selection',mode='erase',selection=expr)]
    alpha=prepare_layer(layer).getchannel('A');assert alpha.getextrema()==(0,255)
    layer.mask_strokes.append(dict(kind='selection',mode='restore_selection',selection=expr))
    assert prepare_layer(layer).getchannel('A').getextrema()==(255,255)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before

def test_selection_boolean_refinement_and_limits():
    a=dict(kind='rectangle',points=[[.1,.1],[.5,.9]])
    b=dict(kind='rectangle',points=[[.4,.2],[.9,.8]])
    assert selection_mask(combine(a,b,'add'),(100,100)).getpixel((80,50))==255
    assert selection_mask(combine(a,b,'subtract'),(100,100)).getpixel((45,50))==0
    assert selection_mask(combine(a,b,'intersect'),(100,100)).getbbox()==(40,20,51,81)
    assert selection_mask(dict(kind='invert',selection=a),(100,100)).getpixel((20,20))==0
    for kind in ('feather','expand','contract'):
        m=selection_mask(dict(kind=kind,selection=a,radius=.03),(100,100));assert m.getbbox()
    m=selection_mask(dict(kind='feather',selection=a,radius=.03),(100,100));assert 0<m.getpixel((9,50))<255
    with pytest.raises(ValueError):selection_mask(dict(kind='rectangle',points=[[float('nan'),0],[1,1]]),(100,100))
    with pytest.raises(ValueError):selection_mask(a,(10000,10000))

def test_selection_restore_baseline_clip_persistence_and_flips(source,tmp_path):
    mask=tmp_path/'mask.png';im=Image.open(source).convert('RGBA');im.putalpha(128);im.save(mask)
    expr=dict(kind='ellipse',points=[[.1,.1],[.5,.9]])
    layer=Layer(str(source),str(mask));layer.mask_strokes=[dict(kind='selection',mode='erase',selection=expr),dict(kind='selection',mode='restore_selection',selection=expr)]
    assert prepare_layer(layer).getchannel('A').getpixel((120,150))==128
    layer.mask_strokes=[dict(mode='erase',points=[[0,.5],[1,.5]],radius=.1,hardness=1,clip_selection=expr)]
    prepared=prepare_layer(layer);assert prepared.getpixel((120,150))[3]==0;assert prepared.getpixel((350,150))[3]==128
    layer.flip_h=True;assert prepare_layer(layer).getpixel((279,150))[3]==0
    photo=Photo(layers=[layer]);loaded=Photo.from_dict(json.loads(json.dumps(asdict(photo))))
    assert prepare_layer(loaded.layers[0]).tobytes()==prepare_layer(layer).tobytes()

@pytest.mark.parametrize('mode,expected',[('auto',90),('none',0),('cw',90),('ccw',270),('half',180)])
@pytest.mark.parametrize('layout',['auto','grid_2x2','custom','max_fit'])
def test_joint_sheet_rotation_geometry_persistence(source,mode,expected,layout):
    p=Photo(kind='Joint composition',width=55,height=45,quantity=19,layers=[Layer(str(source))],print_rotation=mode)
    upright=Photo(width=45,height=55,quantity=4,layers=[Layer(str(source))])
    settings=dict(margin=10,gap_x=.2,gap_y=.2,layout=layout,rows=2,columns=2,auto_rotate_joint=True)
    j=Job(photos=[upright,p],print_settings=settings);j.placements=auto_layout(j.photos,settings);j.page_count=max(r.page for r in j.placements)+1;validate_layout(j)
    copies=[r for r in j.placements if r.photo_id==p.id];assert len(copies)==19
    assert all(r.rotation==expected and (r.width,r.height)==((45,55) if expected in (90,270) else (55,45)) for r in copies)
    assert all(r.rotation==0 for r in j.placements if r.photo_id==upright.id)
    loaded=Job.from_dict(j.to_dict());validate_layout(loaded);assert loaded.to_dict()==j.to_dict()
    assert p.width==55 and p.height==45 and p.layers[0].rotation==0

def test_rotation_old_jobs_and_landscape_unchanged(source):
    p=Photo(kind='Joint',width=55,height=45,layers=[Layer(str(source))]);assert footprint(p,{})==(55,45,0)
    assert footprint(p,dict(auto_rotate_joint=True,landscape=True))==(55,45,0)
    p.width,p.height=45,55;assert footprint(p,dict(auto_rotate_joint=True))==(45,55,0)
    old=Job(photos=[p]).to_dict();old['photos'][0].pop('print_rotation');assert Job.from_dict(old).photos[0].print_rotation=='auto'

@pytest.mark.parametrize('mode,angle',[('cw',90),('ccw',270),('half',180)])
def test_rotated_pdf_exact_matrix_and_preview(source,tmp_path,mode,angle):
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    from app.services.pdf import export_pdf
    from app.ui.canvas import PrintItem
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    p=Photo(width=55,height=45,quantity=1,layers=[Layer(str(source))],print_rotation=mode)
    j=Job(photos=[p],print_settings=dict(margin=10,gap_x=.2,gap_y=.2));j.placements=auto_layout(j.photos,j.print_settings);j.page_count=1
    path=tmp_path/'rotated.pdf';export_pdf(j,path)
    page=PdfReader(path).pages[0];assert float(page.mediabox.width)==pytest.approx(210*72/25.4,abs=.0001)
    operations=ContentStream(page.get_contents(),page.pdf).operations
    matrices=[list(map(float,args)) for args,op in operations if op==b'cm']
    assert any(abs(m[0])<.001 and abs(m[1])==pytest.approx(1) for m in matrices) if angle!=180 else any(m[0]==-1 and m[3]==-1 for m in matrices)
    placement=j.placements[0];item=PrintItem(render_photo(p,100),placement,210,297,lambda:None)
    # The preview's raster and physical footprint rotate together.
    assert item.pixmap().width()/item.pixmap().height()==pytest.approx(placement.width/placement.height,abs=.005)
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtCore import QSize
    from app.services.print_geometry import rotated_image
    pdf=QPdfDocument();assert pdf.load(str(path))==QPdfDocument.Error.None_
    page_image=pdf.render(0,QSize(1680,2376));expected=rotated_image(render_photo(p,100),angle)
    for nx,ny in ((.25,.25),(.75,.25),(.25,.75),(.75,.75)):
        actual=page_image.pixelColor(round((placement.x+nx*placement.width)*8),round((placement.y+ny*placement.height)*8))
        wanted=expected.getpixel((round(nx*(expected.width-1)),round(ny*(expected.height-1))))
        assert all(abs(a-b)<8 for a,b in zip((actual.red(),actual.green(),actual.blue()),wanted))
    pdf.close()

@pytest.fixture
def native_window(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.ui.studio_window import StudioWindow
    app=QApplication.instance() or QApplication([]);monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'appdata'))
    w=StudioWindow();w.show();app.processEvents();yield w
    w.timer.stop();w.pool.waitForDone();app.processEvents();w.invalidate_autosave();w.dirty=False;w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.hardware.printing=False;w.hardware.shutdown();w.close();app.processEvents()

def events(w):
    from PySide6.QtWidgets import QApplication
    end=time.monotonic()+15
    while w.busy and time.monotonic()<end:QApplication.processEvents();time.sleep(.005)
    assert not w.busy;QApplication.processEvents()

def canvas_point(canvas,x,y):
    from PySide6.QtCore import QPointF
    item=canvas.layers[canvas.active];layer=item.layer
    x=1-x if layer.flip_h else x;y=1-y if layer.flip_v else y
    return canvas.mapFromScene(item.mapToScene(QPointF((x-.5)*item.pixmap().width(),(y-.5)*item.pixmap().height())))

@pytest.mark.parametrize('tool',['rectangle','ellipse','lasso','polygon','selection_brush'])
@pytest.mark.parametrize('flips',[(False,False),(True,True)])
def test_native_selection_gestures_transforms_layer_isolation(native_window,source,tool,flips):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w=native_window;w.start_workflow('joint');w.photo.layers=[Layer(str(source),x=.45,y=.55,rotation=31,scale=1.1,flip_h=flips[0],flip_v=flips[1]),Layer(str(source),x=.85,label='Other person')];w.sync_controls();w.timer.stop();w.render_preview();events(w)
    assert 'old background' in w.tool_buttons['restore'].toolTip()
    c=w.canvas;c.scale(1.12,1.12);c.horizontalScrollBar().setValue(c.horizontalScrollBar().value()+3);c.set_tool(tool)
    points=[(.42,.4),(.58,.4),(.58,.6),(.42,.6)] if tool in ('lasso','polygon') else [(.42,.4),(.58,.6)]
    if tool=='polygon':
        for x,y in points:QTest.mouseClick(c.viewport(),Qt.LeftButton,Qt.NoModifier,canvas_point(c,x,y))
        QTest.keyClick(c,Qt.Key_Return)
    else:
        QTest.mousePress(c.viewport(),Qt.LeftButton,Qt.NoModifier,canvas_point(c,*points[0]))
        for p in points[1:]:QTest.mouseMove(c.viewport(),canvas_point(c,*p))
        QTest.mouseRelease(c.viewport(),Qt.LeftButton,Qt.NoModifier,canvas_point(c,*points[-1]))
    assert c.selection and not c.selection_path.isEmpty()
    mask=selection_mask(c.selection,(400,300));assert mask.getpixel((200,150))>0
    QTest.keyClick(c,Qt.Key_Delete);assert len(w.photo.layers[0].mask_strokes)==1 and not w.photo.layers[1].mask_strokes
    assert prepare_layer(w.photo.layers[0]).getchannel('A').getextrema()[0]==0
    w.timer.stop();w.undo_edit();assert not w.photo.layers[0].mask_strokes
    w.redo_edit();assert len(w.photo.layers[0].mask_strokes)==1
    w.timer.stop();events(w)

def test_selection_saved_reopened_discard_and_lock(native_window,source,monkeypatch):
    from app.services.selections import selection_mask
    w=native_window;w.start_workflow('portrait');w.photo.layers=[Layer(str(source))];w.sync_controls();w.timer.stop();w.render_preview();events(w)
    c=w.canvas;c.modify_selection('all');c.edit_selection();assert w.save_job();identity=w.job.id
    original=w.db.load_job(identity).to_dict();c.edit_selection(True);assert len(w.photo.layers[0].mask_strokes)==2
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Discard)
    w.timer.stop();assert w.save_before_leave();assert w.job.to_dict()==original
    w.timer.stop();events(w)
    w.photo.layers[0].locked=True;w.render_preview();events(w);count=len(w.photo.layers[0].mask_strokes);c.edit_selection();assert len(w.photo.layers[0].mask_strokes)==count
    loaded=w.db.load_job(identity);assert prepare_layer(loaded.photos[0].layers[0]).getchannel('A').getextrema()==(0,0)

def test_selection_complexity_and_long_stroke_performance():
    expression=dict(kind='selection_brush',points=[[i/2000,.5+.15*math.sin(i/30)] for i in range(2000)],radius=.005)
    start=time.monotonic();mask=selection_mask(expression,(1400,1000));assert mask.getbbox();assert time.monotonic()-start<3
    node={'kind':'all'}
    for _ in range(34):node={'kind':'invert','selection':node}
    with pytest.raises(ValueError,match='complex'):selection_mask(node,(50,50))

def test_print_transaction_uncertainty_acknowledgment_and_repeat(source,tmp_path):
    from app.services.print_transactions import unresolved,acknowledge,repeat_sheets,profile_key
    root=tmp_path/'app';folder=root/'print-spool'/'unknown';folder.mkdir(parents=True);ledger=folder/'status.json';ledger.write_text('{"status":"submitting; physical output unknown"}')
    assert unresolved(root)==[ledger];before=ledger.read_bytes();acknowledge(unresolved(root));assert not unresolved(root) and ledger.read_bytes()==before
    p=Photo(layers=[Layer(str(source))],quantity=4);j=Job(photos=[p],print_settings=dict(margin=10,gap_x=.2,gap_y=.2));j.placements=auto_layout(j.photos,j.print_settings)
    result=repeat_sheets(j,3);assert result.page_count==3 and result.photos[0].quantity==12;assert len(result.placements)==12;validate_layout(result)
    assert j.photos[0].quantity==4 and len(j.placements)==4
    assert profile_key(j,'color')!=profile_key(j,'gray')
    from app.services.hardware import validate_hardware_setting
    with pytest.raises(ValueError):validate_hardware_setting('preferred_print_color','mono')
    assert validate_hardware_setting('document_color','mono')=='mono'

@pytest.mark.parametrize('quick,known,status,expected',[(False,False,'Ready',False),(True,False,'Ready',False),(True,True,'Ready',True),(True,True,'Offline',False),(True,True,'Queue available; physical readiness unverified',False)])
def test_consolidated_print_and_quick_safety(native_window,source,monkeypatch,quick,known,status,expected):
    from PySide6.QtWidgets import QMessageBox
    from app.ui.hardware_process import HardwareProcess
    from app.services.print_transactions import profile_key
    highres=source.parent/'print-resolution.png';Image.new('RGB',(1800,2200),'white').save(highres)
    w=native_window;h=w.hardware;p=Photo(layers=[Layer(str(highres))]);j=Job(photos=[p],print_settings=dict(margin=10,gap_x=.2,gap_y=.2))
    h.printers=[dict(id='Simulated',name='Simulated',status=status,default=True)];h.populate(h.printer,h.printers,'Simulated','None')
    w.db.set('quick_print',quick)
    if known:w.db.set('confirmed_print_profiles',{'Simulated':[profile_key(j)]})
    calls=[];monkeypatch.setattr(HardwareProcess,'start',lambda self,*a:calls.append(a));monkeypatch.setattr(w,'run',lambda fn,done,*_:done(fn()))
    monkeypatch.setattr(QMessageBox,'question',lambda *a:pytest.fail('Print button must be the sole confirmation'))
    h.print_job(j);d=h.print_dialog;d.result({'area':dict(left=0,top=0,right=210,bottom=297)})
    assert bool([r for r in calls if r[1].get('action')=='print'])==expected
    if status=='Ready' and not expected:d.print_now()
    if status=='Ready':
        d.print_now();assert len([r for r in calls if r[1].get('action')=='print'])==1
        d.result({'status':'Submitted to driver; physical output unconfirmed'});assert d.state=='SubmittedToDriver' and not h.printing

def test_unknown_print_blocks_new_request_and_records_failure(native_window,source,tmp_path,monkeypatch):
    from app.ui.hardware import PrintDialog
    from app.ui.hardware_process import HardwareProcess
    from app.services.pdf import export_pdf
    from app.core.database import data_root
    root=data_root();f=root/'print-spool'/'previous';f.mkdir(parents=True);(f/'status.json').write_text('{"status":"submission uncertain"}')
    p=Photo(layers=[Layer(str(source))]);j=Job(photos=[p],print_settings=dict(margin=10,gap_x=.2,gap_y=.2));j.placements=auto_layout(j.photos,j.print_settings)
    folder=root/'print-spool'/'current';folder.mkdir();export_pdf(j,folder/'sheet.pdf')
    h=native_window.hardware;h.printers=[dict(id='Fake',name='Fake',status='Ready',default=True)];calls=[];monkeypatch.setattr(HardwareProcess,'start',lambda self,*a:calls.append(a))
    d=PrintDialog(h,j,folder);h.print_dialog=d;d.auto_requested=True;d.result({'area':dict(left=0,top=0,right=210,bottom=297)})
    assert not d.submit.isEnabled() and d.ack.isVisible();d.print_now();assert not any(a[1]['action']=='print' for a in calls)
    d.acknowledge_unknown();d.result({'area':dict(left=0,top=0,right=210,bottom=297)});d.print_now();assert d.attempted
    (folder/'status.json').write_text('{"status":"submitting; physical output unknown"}');d.error('Driver timed out');assert d.state=='OutcomeUnknown';d.print_now();assert len([a for a in calls if a[1]['action']=='print'])==1

def test_print_setup_orientation_and_sheet_sets_preserve_active_document(native_window,source,tmp_path,monkeypatch):
    from app.ui.hardware import PrintDialog
    from app.ui.hardware_process import HardwareProcess
    from app.services.pdf import export_pdf
    from pypdf import PdfReader
    w=native_window;h=w.hardware;h.printers=[dict(id='Fake',name='Fake',status='Ready',default=True)]
    monkeypatch.setattr(HardwareProcess,'start',lambda *args:None)
    monkeypatch.setattr(w,'run',lambda fn,done,*args:done(fn()))
    p=Photo(layers=[Layer(str(source))],quantity=4);j=Job(photos=[p],print_settings=dict(margin=10,gap_x=.2,gap_y=.2));j.placements=auto_layout(j.photos,j.print_settings);original=j.to_dict();active=w.job.to_dict()
    folder=tmp_path/'print-setup';folder.mkdir();export_pdf(j,folder/'sheet.pdf');d=PrintDialog(h,j,folder)
    d.result({'area':dict(left=0,top=0,right=210,bottom=297)});d.orientation.setCurrentIndex(1);d.orientation.activated.emit(1)
    assert d.job.print_settings['landscape'];d.result({'area':dict(left=0,top=0,right=297,bottom=210)})
    d.sets.setValue(3);assert d.job.page_count==3 and d.job.photos[0].quantity==12
    assert len(PdfReader(d.pdf_path).pages)==3;assert d.pdf_path!=folder/'sheet.pdf';validate_layout(d.job)
    assert w.job.to_dict()==active and j.to_dict()==original

def test_processing_brush_feather_and_opacity_are_saved(source):
    layer=Layer(str(source));layer.mask_strokes=[dict(mode='erase',points=[[.3,.5],[.7,.5]],radius=.04,hardness=1,opacity=.5,feather=.015)]
    result=prepare_layer(layer);assert 120<=result.getpixel((200,150))[3]<=135
    assert 135<result.getpixel((200,170))[3]<255
    restored=Layer(**json.loads(json.dumps(asdict(layer))));assert prepare_layer(restored).tobytes()==result.tobytes()

def test_new_jobs_default_rotation_and_historical_jobs_do_not(native_window,source):
    w=native_window;w.start_workflow('joint');assert w.job.print_settings['auto_rotate_joint'] is True
    w.photo.layers=[Layer(str(source))];assert footprint(w.photo,w.job.print_settings)==(45,55,90)
    historical=Job(photos=[copy.deepcopy(w.photo)]);historical.placements=auto_layout(historical.photos,historical.print_settings)
    assert all(r.rotation==0 and r.width==55 for r in historical.placements)
    w.dirty=False;w.adopt_job(Job.from_dict(historical.to_dict()));w.sync_controls();assert not w.print_options.auto_rotate_joint.isChecked()
    assert w.studio.multi.empty_job().print_settings['auto_rotate_joint'] is True

@pytest.mark.parametrize('size',[(1050,740),(1366,768),(1920,1080)])
def test_active_workspaces_do_not_inherit_hidden_page_minimum(native_window,size):
    from PySide6.QtWidgets import QApplication
    w=native_window;w.setFixedSize(*size)
    for page in (w.stack.widget(1),w.hardware.scan_dialog,w.studio.multi,w.shell.copy,w.shell.nid):
        w.stack.setCurrentWidget(page)
        for _ in range(8):QApplication.processEvents()
        minimum=page.minimumSizeHint();view=w.shell.workspace_scroll.viewport().size()
        assert w.stack.size().height()<=max(view.height(),minimum.height())+1
        assert w.stack.size().width()<=max(view.width(),minimum.width())+1
    assert all(w.shell.navigation.item(i).text() for i in range(13))
