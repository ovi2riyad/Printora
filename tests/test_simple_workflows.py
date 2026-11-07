"""Simplified page controls and one-click document requests. No physical device use."""
import copy,json,time,hashlib
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from pypdf import PdfReader
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from app.services.documents import detect_cards


def wait(w):
    end=time.monotonic()+30
    while w.busy and time.monotonic()<end:QApplication.processEvents();time.sleep(.005)
    assert not w.busy
    for _ in range(5):QApplication.processEvents()


@pytest.fixture
def studio(tmp_path,monkeypatch):
    from app.ui.studio_window import StudioWindow
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);calls=[];errors=[]
    monkeypatch.setattr(HardwareProcess,'start',lambda self,*args:calls.append(args))
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(str(a[-1])))
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Discard)
    w=StudioWindow();w.show();app.processEvents()
    h=w.hardware;h.scanners=[dict(id='FAKE',name='Simulated scanner',status='Simulated',backend='wia')]
    h.printers=[dict(id='FAKE-PRINTER',name='Simulated printer',status='Ready',default=True)]
    h.populate(h.scanner,h.scanners,'FAKE','None');h.populate(h.printer,h.printers,'FAKE-PRINTER','None')
    h.scan_dialog.update_devices();h.scan_dialog.result('capabilities',dict(sources=[dict(id='bed',name='Flatbed',width_mm=215.9,height_mm=296.926,resolutions=[100,150,300,600],colors=['color','gray'])],status='Test'))
    w.shell.copy.update_printers();w.shell.nid.update_printers()
    yield w,calls,errors
    wait(w)
    for doc in (w.shell.copy,w.shell.nid):
        if doc.preview_dialog:doc.preview_dialog.close()
        doc.advanced_settings.hide();doc.dirty=False;doc.simple_inflight=False
    w.photo_settings.hide();w.timer.stop();w.invalidate_autosave();w.dirty=False;w.close();app.processEvents()
    assert not errors,errors


def fake_transfer(w,path,color='white',flags=None):
    Image.new('RGB',(620,877),color).save(path,dpi=(150,150))
    request=w.hardware.scan_request
    record=dict(original=str(path),width=620,height=877,format='PNG',driver=dict(dpi=request['dpi'],**(flags or {})))
    callback=w.hardware.scan_dialog.completion_callback
    assert callback is not None
    callback(record);wait(w)
    return record


def test_scan_main_only_exposes_scanner_resolution_and_a4(studio):
    w,calls,errors=studio;d=w.hardware.scan_dialog;w.stack.setCurrentWidget(d);QApplication.processEvents()
    assert d.device.isVisible() and d.dpi.isVisible() and d.dpi.currentData()==300
    assert [v.value() for v in d.region]==[0,0,210,296.926]
    assert not d.color.isVisible() and not d.source.isVisible() and not d.area_presets.isVisible()
    assert d.preview_button.isVisible() and d.scan_button.isVisible()
    d.advanced_settings.open_settings();QApplication.processEvents()
    assert d.color.isVisible() and d.source.isVisible() and d.area_presets.isVisible()


def test_quick_copy_main_controls_and_settings_are_not_duplicated(studio):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);QApplication.processEvents()
    assert c.color_copy.isVisible() and c.bw_copy.isVisible() and c.print_set_button.isVisible()
    assert c.scanner.isVisible() and c.printer.isVisible() and c.fields['copies'].isVisible()
    assert c.fields['scan_dpi'].value()==150 and not c.fields['scan_dpi'].isVisible()
    assert not c.primary_print.isVisible() and not c.color.isVisible()
    assert not w.shell.toolbar_actions['print'].isVisible()
    c.advanced_settings.open_settings();QApplication.processEvents()
    assert c.fields['scan_dpi'].isVisible() and c.primary_print.isVisible()


@pytest.mark.parametrize('color',['color','gray'])
def test_single_copy_scans_at_150_a4_and_submits_new_page_once(studio,tmp_path,monkeypatch,color):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);printed=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda job,**kw:printed.append((job,kw)))
    c.fields['copies'].setValue(3);previous=w.db.get('scan_dpi',300)
    c.start_copy(color);request=w.hardware.scan_request
    assert request['dpi']==150 and request['color']==color and request['region']==[0,0,210,296.926]
    assert w.db.get('scan_dpi',300)==previous and not c.color_copy.isEnabled()
    path=tmp_path/'retained-scan.png';fake_transfer(w,path);before=path.read_bytes()
    assert len(printed)==1
    job,kw=printed[0];assert job.page_count==3 and len(job.photos)==1 and job.photos[0].quantity==3
    assert kw==dict(direct=True,driver_color=color,printer_id='FAKE-PRINTER')
    c.simple_pending=None;QApplication.processEvents();assert len(printed)==1 and path.read_bytes()==before


def test_set_add_then_finish_is_collated_and_never_submits_early(studio,tmp_path,monkeypatch):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);printed=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda job,**kw:printed.append((job,kw)))
    c.fields['copies'].setValue(2);c.start_copy('color',True)
    c.finish_set();assert not printed # No page has finished yet.
    first=tmp_path/'scan-one.png';fake_transfer(w,first,'red')
    assert not printed and c.set_active and c.add_page_button.isEnabled() and c.finish_set_button.isEnabled()
    c.add_set_page();second=tmp_path/'scan-two.png';fake_transfer(w,second,'blue')
    assert len(c.copy_batch)==2 and not printed
    c.finish_set();c.finish_set();wait(w)
    assert len(printed)==1 and not c.set_active
    job,kw=printed[0];assert job.page_count==4 and len(job.photos)==2 and kw['direct'] is True
    assert [p.copy for p in job.placements]==[0,0,1,1]
    assert first.exists() and second.exists()


def test_full_a4_scan_uses_explicit_fit_default_and_can_print(studio,tmp_path,monkeypatch):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);printed=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda job,**kw:printed.append(job) or True)
    c.start_copy('color');path=tmp_path/'full-a4.png';Image.new('RGB',(1240,1754),'white').save(path,dpi=(150,150))
    w.hardware.scan_dialog.completion_callback(dict(original=str(path),driver=dict(dpi=150)));wait(w)
    assert c.scale_mode.currentData()=='fit' and len(printed)==1
    placement=printed[0].placements[0];assert placement.width<=190 and placement.height<=277
    assert 'Fit' in c.settings_summary.text()


def test_bad_geometry_retains_scan_set_for_settings_fix_without_rescanning(studio,tmp_path,monkeypatch):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);printed=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda job,**kw:printed.append(job) or True)
    c.start_copy('color',True);path=tmp_path/'a4.png';Image.new('RGB',(1240,1754),'white').save(path,dpi=(150,150))
    w.hardware.scan_dialog.completion_callback(dict(original=str(path),driver=dict(dpi=150)));wait(w)
    c.scale_mode.setCurrentIndex(c.scale_mode.findData('actual'));c.finish_set();wait(w)
    assert not printed and c.set_active and len(c.copy_batch)==1 and path.exists()
    assert len(errors)==1 and 'margins' in errors[0];errors.clear()
    count=len([r for kind,r,*_ in calls if r['action']=='scan'])
    c.scale_mode.setCurrentIndex(c.scale_mode.findData('fit'));c.finish_set();wait(w)
    assert len(printed)==1 and len([r for kind,r,*_ in calls if r['action']=='scan'])==count


def test_unsupported_copy_dpi_stops_before_acquisition_and_preserves_scan_defaults(studio):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);d=w.hardware.scan_dialog
    d.sources[0]['resolutions']=[100,300];c.start_copy('gray')
    assert not [r for kind,r,*_ in calls if r['action']=='scan']
    assert not c.simple_inflight and not c.set_active and c.color_copy.isEnabled()
    assert 'resolution' in d.message.text() and w.db.get('scan_dpi',300)==300


@pytest.mark.parametrize('flags',[dict(canceled=True),dict(partial=True),dict(warning='Feeder stopped')])
def test_incomplete_single_scan_is_retained_without_automatic_submission(studio,tmp_path,monkeypatch,flags):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);printed=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda *a,**k:printed.append(a))
    c.start_copy('gray');path=tmp_path/'partial.png';fake_transfer(w,path,flags=flags)
    assert not printed and path.exists() and c.session.pages and not c.simple_inflight


def test_scan_error_restores_actions_and_does_not_print(studio,monkeypatch):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c);printed=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda *a,**k:printed.append(a))
    c.start_copy('color',True);w.hardware.scan_dialog.error('Simulated failure')
    assert not c.simple_inflight and not c.set_active and c.color_copy.isEnabled() and not printed


def test_late_scan_delivery_waits_for_gui_worker_and_discard_invalidates_it(studio,tmp_path,monkeypatch):
    w,calls,errors=studio;c=w.shell.copy;w.shell.open(c)
    monkeypatch.setattr(w.hardware,'print_job',lambda *a,**k:None)
    c.start_copy('color',True);callback=w.hardware.scan_dialog.completion_callback
    path=tmp_path/'queued.png';Image.new('RGB',(100,140),'red').save(path)
    record=dict(original=str(path),driver=dict(dpi=150));w.busy=True;callback(record)
    assert c.pending_delivery and not c.session.pages
    w.busy=False;c.deliver_scan();wait(w);assert len(c.session.pages)==1 and path.exists()
    c.simple_inflight=False;assert c.clear(confirm=False);assert not c.pending_delivery and not c.set_active and path.exists()
    callback(record);wait(w);assert not c.session.pages # Old scan token cannot repopulate cleared work.


def card(path,color='blue',box=(100,150,900,650),size=(1000,800)):
    image=Image.new('RGB',size,'white');draw=ImageDraw.Draw(image);draw.rectangle(box,fill=color,outline='black',width=5);image.save(path,dpi=(300,300));return path


def import_nid(w,paths):
    n=w.shell.nid;w.shell.open(n);n.import_files(paths=[str(p) for p in paths]);wait(w)
    assert n.preview_dialog and n.preview_dialog.job
    return n,n.preview_dialog


def test_two_nid_files_auto_detect_both_sides_and_open_exact_pdf(studio,tmp_path):
    w,calls,errors=studio;front=card(tmp_path/'front.png');back=card(tmp_path/'back.png','orange',box=(180,220,820,620))
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (front,back)]
    n,p=import_nid(w,[front,back]);assert len(n.session.pages)==2 and all(page.points for page in n.session.pages)
    assert n.reviewed=={id(page) for page in n.session.pages} and len(p.handles)==2 and all(len(h)==4 for h in p.handles.values())
    assert len(PdfReader(p.path).pages)==1
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in zip((front,back),hashes))


def test_combined_scan_splits_front_back_without_modifying_original(studio,tmp_path):
    w,calls,errors=studio;path=tmp_path/'both.png';image=Image.new('RGB',(1200,1600),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((100,100,1100,700),fill='blue',outline='black',width=5);draw.rectangle((150,900,1050,1450),fill='orange',outline='black',width=5);image.save(path,dpi=(300,300));before=path.read_bytes()
    assert len(detect_cards(image))==2
    n,p=import_nid(w,[path]);assert len(n.session.pages)==2 and [page.label for page in n.session.pages]==['Front','Back']
    assert n.session.pages[0].points!=n.session.pages[1].points and path.read_bytes()==before


def test_supplied_nid_sides_open_full_card_pdf_instead_of_whole_scan(studio):
    root=Path(__file__).resolve().parents[1]/'Demo/nid';paths=[root/'front.jpg',root/'back.jpg']
    if not all(p.is_file() for p in paths):pytest.skip('Private studio scans absent')
    w,calls,errors=studio;before=[p.read_bytes() for p in paths];n,p=import_nid(w,paths)
    import cv2
    from app.services.cropping import order_quad
    assert all(len(page.points)==4 and cv2.contourArea(order_quad(page.points))>590_000 for page in n.session.pages)
    assert len(p.handles)==2 and p.job.page_count==1
    assert all(80<photo.width<87 and 49<photo.height<55 for photo in p.job.photos)
    assert [path.read_bytes() for path in paths]==before


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_native_nid_corner_drag_reveals_scan_and_updates_pdf_only(studio,tmp_path,rotation):
    w,calls,errors=studio;paths=[card(tmp_path/'front.png'),card(tmp_path/'back.png','orange')];before=[p.read_bytes() for p in paths]
    n,p=import_nid(w,paths);n.session.pages[0].rotation=rotation;p.rebuild();wait(w)
    page=n.session.pages[0];old=copy.deepcopy(page.points);old_pdf=p.path;handle=p.handles[0][0]
    QTest.qWait(40)
    start=p.view.mapFromScene(handle.scenePos());end=start+QPoint(15,12)
    QTest.mousePress(p.view.viewport(),Qt.LeftButton,Qt.NoModifier,start)
    assert p.overlay is not None and p.overlay.opacity()==pytest.approx(.35) and p.overlay_side==0
    QTest.mouseMove(p.view.viewport(),end,30);QTest.mouseRelease(p.view.viewport(),Qt.LeftButton,Qt.NoModifier,end);wait(w)
    assert page.points!=old and p.path!=old_pdf and len(PdfReader(p.path).pages)==1,p.status.text()
    assert [path.read_bytes() for path in paths]==before


def test_nid_preview_print_is_one_direct_request_and_rebuilds_stale_settings(studio,tmp_path,monkeypatch):
    w,calls,errors=studio;n,p=import_nid(w,[card(tmp_path/'f.png'),card(tmp_path/'b.png','orange')]);printed=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda job,**kw:printed.append((job,kw)) or True)
    n.fields['spacing'].setValue(20);p.print_pdf();wait(w);p.print_pdf()
    assert len(printed)==1 and printed[0][1]['direct'] is True and printed[0][1]['printer_id']=='FAKE-PRINTER'
    front,back=printed[0][0].placements;assert back.y-front.y-front.height==pytest.approx(20)
    assert (front.y+back.y+back.height)/2==pytest.approx(148.5)


def test_nid_settings_close_regenerates_pdf_and_click_without_drag_keeps_overlay(studio,tmp_path):
    w,calls,errors=studio;n,p=import_nid(w,[card(tmp_path/'f.png'),card(tmp_path/'b.png','orange')])
    old=p.path;n.advanced_settings.open_settings();n.fields['spacing'].setValue(17);n.advanced_settings.hide();wait(w)
    assert p.path!=old and p.job.placements[1].y-p.job.placements[0].y-p.job.placements[0].height==pytest.approx(17)
    handle=p.handles[0][0];position=p.view.mapFromScene(handle.scenePos());old=p.path
    QTest.mouseClick(p.view.viewport(),Qt.LeftButton,Qt.NoModifier,position);QApplication.processEvents()
    assert p.overlay is not None and p.path==old


def test_nid_rejected_print_request_keeps_retry_available(studio,tmp_path,monkeypatch):
    w,calls,errors=studio;n,p=import_nid(w,[card(tmp_path/'f.png'),card(tmp_path/'b.png','orange')])
    monkeypatch.setattr(w.hardware,'print_job',lambda *a,**kw:False);p.print_pdf()
    assert not p.printed and p.print_button.isEnabled()


def test_nid_invalid_corner_does_not_replace_previous_pdf_or_crop(studio,tmp_path):
    w,calls,errors=studio;n,p=import_nid(w,[card(tmp_path/'f.png'),card(tmp_path/'b.png','orange')]);old=copy.deepcopy(n.session.pages[0].points);path=p.path
    for h in p.handles[0]:h.setPos(p.handles[0][0].pos())
    p.commit(0);wait(w)
    assert p.path==path and n.session.pages[0].points==old


def test_missing_selected_printer_never_falls_back_to_another_device(studio,tmp_path):
    from app.ui.hardware import PrintDialog
    from app.services.documents import DocumentSession
    from app.services.pdf import export_pdf
    w,calls,errors=studio;path=tmp_path/'doc.png';Image.new('RGB',(200,300)).save(path);s=DocumentSession(tmp_path);s.import_image(path,dpi=150);job=s.job(dict(copies=1));spool=tmp_path/'spool';spool.mkdir();export_pdf(job,spool/'sheet.pdf')
    calls.clear();dialog=PrintDialog(w.hardware,job,spool,printer_id='REMOVED-PRINTER')
    assert dialog.printer.currentData() is None and not calls
    assert not dialog.submit.isEnabled();dialog.close()


def test_workspace_defaults_roundtrip_and_invalid_optional_values_are_retained(studio):
    w,calls,errors=studio;c=w.shell.copy;c.fields['scan_dpi'].setValue(300);c.fields['copies'].setValue(4);c.save_defaults()
    assert w.db.get('workflow_defaults')['copy']['scan_dpi']==300
    from app.ui.document_studio import DocumentStudio
    reopened=DocumentStudio(w,'copy');assert reopened.fields['scan_dpi'].value()==300 and reopened.fields['copies'].value()==4;reopened.shutdown();reopened.deleteLater()
    raw=json.dumps({'copy':dict(scan_dpi=True),'nid':dict(center=True,spacing=12)})
    with w.db.conn:w.db.conn.execute('UPDATE config SET value=? WHERE key=?',(raw,'workflow_defaults'))
    assert w.db.get('workflow_defaults')=={'nid':dict(center=True,spacing=12)}
    assert w.db.conn.execute('SELECT value FROM config WHERE key=?',('workflow_defaults',)).fetchone()[0]==raw


def test_portrait_has_top_preview_quantity_and_advanced_settings(studio):
    w,calls,errors=studio;w.start_workflow('portrait');QApplication.processEvents()
    assert w.quantity.isVisible() and w.top_preview.isVisible() and w.photo_settings_button.isVisible()
    assert w.profile_picker.isVisible() and w.border.isVisible() and not w.scale.isVisible()
    w.quantity.setValue(6);assert w.photo.quantity==6
    w.photo_settings.open_settings();QApplication.processEvents();assert w.scale.isVisible()


@pytest.mark.parametrize('status,expected',[('Ready',1),('Queue available; physical readiness unverified',1),('Offline',0),('Error',0)])
def test_explicit_copy_or_finish_request_submits_once_without_second_confirmation(studio,tmp_path,monkeypatch,status,expected):
    from app.ui.hardware import PrintDialog
    from app.ui.hardware_process import HardwareProcess
    from app.services.documents import DocumentSession
    from app.services.pdf import export_pdf
    w,calls,errors=studio;path=tmp_path/'doc.png';Image.new('RGB',(200,300),'white').save(path);s=DocumentSession(tmp_path);s.import_image(path,dpi=150);job=s.job(dict(copies=1));spool=tmp_path/'spool';spool.mkdir();export_pdf(job,spool/'sheet.pdf')
    w.hardware.printers[0]['status']=status
    dialog=PrintDialog(w.hardware,job,spool,printer_id='FAKE-PRINTER');dialog.auto_requested=True;dialog.direct_requested=True
    dialog.result(dict(area=dict(left=0,top=0,right=210,bottom=297)))
    requests=[args[1] for args in calls if args[1]['action']=='print'];assert len(requests)==expected
    if expected:assert requests[0]['automatic'] is False
    dialog.close();w.hardware.printing=False
