"""Native pointer/keyboard workflows; scanner transfers are simulated, never acquired."""
import hashlib
import json
import time
import pytest
from PIL import Image
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox,QLabel
from app.models.domain import Layer
from app.services.hardware import validate_hardware_setting
from app.services.imaging import prepare_layer
from app.services.selections import selection_mask

@pytest.fixture
def window(tmp_path,monkeypatch):
    from app.ui.hardware_process import HardwareProcess
    from app.ui.studio_window import StudioWindow
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user-data'))
    monkeypatch.setattr(HardwareProcess,'start',lambda *a:None)
    w=StudioWindow();w.show();app.processEvents()
    yield w
    w.timer.stop();w.pool.waitForDone();app.processEvents();w.invalidate_autosave();w.dirty=False;w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.hardware.shutdown();w.close();app.processEvents()

def settle(w):
    deadline=time.monotonic()+20
    while w.busy and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
    assert not w.busy;QApplication.processEvents()

def point(canvas,x,y):
    item=canvas.layers[canvas.active];layer=item.layer
    if layer.flip_h:x=1-x
    if layer.flip_v:y=1-y
    return canvas.mapFromScene(item.mapToScene(QPointF((x-.5)*item.pixmap().width(),(y-.5)*item.pixmap().height())))

def drag(c,start,end,modifiers=Qt.NoModifier):
    QTest.mousePress(c.viewport(),Qt.LeftButton,modifiers,start);QTest.mouseMove(c.viewport(),end,30);QTest.mouseRelease(c.viewport(),Qt.LeftButton,modifiers,end);QApplication.processEvents()

@pytest.mark.parametrize('tool',['rectangle','ellipse','square','circle'])
@pytest.mark.parametrize('flip,rotation',[(False,0),(True,31)])
def test_shift_and_explicit_shapes_are_square_in_source_pixels(window,tmp_path,tool,flip,rotation):
    source=tmp_path/'source.png';Image.new('RGBA',(600,400),'red').save(source);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    w=window;w.start_workflow('portrait');w.photo.layers=[Layer(str(source),rotation=rotation,flip_h=flip)];w.sync_controls();w.timer.stop();w.render_preview();settle(w)
    index=w.shape_picker.findData(tool);w.shape_picker.setCurrentIndex(index);w.shape_picker.activated.emit(index)
    c=w.canvas;drag(c,point(c,.4,.4),point(c,.55,.48),Qt.ShiftModifier if tool in ('rectangle','ellipse') else Qt.NoModifier)
    expr=c.selection;assert expr['kind'] in ('rectangle','ellipse');a,b=expr['points'];assert abs(b[0]-a[0])*600==pytest.approx(abs(b[1]-a[1])*400,abs=2)
    assert 'constrain' not in expr
    mask=selection_mask(expr,(600,400));bounds=mask.getbbox();assert abs((bounds[2]-bounds[0])-(bounds[3]-bounds[1]))<=2
    QTest.keyClick(c,Qt.Key_Delete);assert len(w.photo.layers[0].mask_strokes)==1;assert prepare_layer(w.photo.layers[0]).getchannel('A').getextrema()==(0,255)
    w.timer.stop();w.undo_edit();settle(w);assert not w.photo.layers[0].mask_strokes
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest

def test_ctrl_shift_adds_constrained_shape_without_replacing_first(window,tmp_path):
    p=tmp_path/'p.png';Image.new('RGB',(600,400),'blue').save(p)
    w=window;w.start_workflow('portrait');w.photo.layers=[Layer(str(p))];w.sync_controls();w.timer.stop();w.render_preview();settle(w);c=w.canvas;c.set_tool('rectangle')
    drag(c,point(c,.3,.3),point(c,.4,.4));first=c.selection
    drag(c,point(c,.55,.55),point(c,.65,.6),Qt.ControlModifier|Qt.ShiftModifier)
    assert c.selection['kind']=='add' and c.selection['left']==first
    a,b=c.selection['right']['points'];assert abs(b[0]-a[0])*600==pytest.approx(abs(b[1]-a[1])*400,abs=2)
    mask=selection_mask(c.selection,(600,400));assert mask.getpixel((210,140)) and mask.getpixel((350,240))
    drag(c,point(c,.45,.45),point(c,.5,.5),Qt.ShiftModifier);assert c.selection['kind']=='rectangle' # Shift constrains; it does not add.
    assert w.editor_tools.advanced.isHidden()

def scanner(w,monkeypatch,width=230,height=330):
    d=w.hardware.scan_dialog;h=w.hardware
    h.scanners=[dict(id='SIMULATED',name='Simulated scanner — no acquisition',status='Detected',backend='wia')];h.populate(h.scanner,h.scanners,'SIMULATED','None');d.update_devices()
    caps=dict(id='flatbed',name='Flatbed',width_mm=width,height_mm=height,resolutions=[100,300,600],colors=['color','gray'])
    calls=[];monkeypatch.setattr(h.scan_process,'start',lambda *args:calls.append(args))
    d.result('capabilities',dict(sources=[caps],status='Simulated'));w.stack.setCurrentWidget(d);QApplication.processEvents()
    return d,caps,calls

def test_preview_then_drag_scans_only_selected_area_without_checkbox(window,monkeypatch):
    d,caps,calls=scanner(window,monkeypatch)
    d.set_region([5,6,60,70]);d.scan_now(preview=True)
    request=calls[-1][1];assert request['region']==[0,0,230,330] and request['dpi']==100
    assert window.db.get('scan_region')==[5,6,60,70]
    d.set_scanning(False);d.display_preview(Image.new('RGB',(690,990),'white'))
    c=d.preview_canvas;assert c.draw_mode;drag(c,c.mapFromScene(QPointF(69,99)),c.mapFromScene(QPointF(345,594)))
    actual=[box.value() for box in d.region];assert actual==pytest.approx([23,33,92,165],abs=1.5)
    assert d.apply_area.isChecked() and d.apply_area.isHidden() and d.advanced_area.isHidden()
    d.scan_now();assert calls[-1][1]['region']==actual and calls[-1][1]['dpi']==300
    assert all(not box.isEnabled() for box in d.region) and not d.paper.isEnabled() and not d.preview_button.isEnabled()

@pytest.mark.parametrize('paper,expected',[(1,[0,0,210,297]),(2,[0,0,215.9,279.4])])
def test_paper_shortcuts_and_exact_driver_request(window,monkeypatch,paper,expected):
    d,caps,calls=scanner(window,monkeypatch);d.paper.setCurrentIndex(paper);d.paper.activated.emit(paper)
    assert [b.value() for b in d.region]==expected
    d.scan_now();assert calls[-1][1]['region']==expected

def test_paper_too_large_does_not_clip_or_change_previous_region(window,monkeypatch):
    d,caps,calls=scanner(window,monkeypatch,210,297);before=[b.value() for b in d.region]
    d.paper_changed(2);assert [b.value() for b in d.region]==before and 'does not fit' in d.message.text()
    assert not calls

def test_a4_short_driver_bed_uses_reported_extent_with_notice(window,monkeypatch):
    d,_,calls=scanner(window,monkeypatch,215.9,296.926);d.paper_changed(1)
    assert [b.value() for b in d.region]==[0,0,210,296.926] and 'Driver usable area' in d.message.text()
    d.dpi.setCurrentIndex(d.dpi.findData(600));d.scan_now();assert calls[-1][1]['region']==[0,0,210,296.926]

def test_named_area_persistence_reuse_scoping_and_validation(window,monkeypatch):
    d,caps,calls=scanner(window,monkeypatch);region=[12,18,90,110];d.set_region(region)
    monkeypatch.setattr(QInputDialog,'getText',lambda *a:('Passport sheet',True));d.save_area()
    raw=window.db.get('scan_area_presets');assert raw['Passport sheet']['region']==region
    from app.core.database import Database
    db=Database(window.db.path);assert db.get('scan_area_presets')==raw;db.conn.close()
    d.full_bed();d.refresh_area_presets();index=d.area_presets.findData('Passport sheet');d.area_presets.setCurrentIndex(index);d.area_presets.activated.emit(index)
    assert [b.value() for b in d.region]==region
    # Capability refresh must not replace the chosen area before final acquisition.
    d.capability_time=0;d.scan_now();assert calls[-1][1]['action']=='capabilities'
    d.result('capabilities',dict(sources=[caps],status='Simulated'));assert calls[-1][1]['region']==region
    d.set_scanning(False);d.area_context=('another scanner','flatbed');d.refresh_area_presets();assert d.area_presets.count()==1
    d.area_context=('SIMULATED','flatbed');d.refresh_area_presets();caps['width_mm']=80;before=[b.value() for b in d.region];d.use_preset(d.area_presets.findData('Passport sheet'))
    assert [b.value() for b in d.region]==before and 'beyond' in d.message.text()

def test_preset_cancel_replace_and_remove_do_not_touch_scans(window,monkeypatch,tmp_path):
    d,_,_=scanner(window,monkeypatch);asset=tmp_path/'original.bmp';Image.new('RGB',(20,30),'red').save(asset);before=asset.read_bytes()
    monkeypatch.setattr(QInputDialog,'getText',lambda *a:('My area',False));d.save_area();assert window.db.get('scan_area_presets',{})=={}
    monkeypatch.setattr(QInputDialog,'getText',lambda *a:('My area',True));d.set_region([0,0,40,50]);d.save_area();first=window.db.get('scan_area_presets')
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.No);d.set_region([0,0,80,100]);d.save_area();assert window.db.get('scan_area_presets')==first
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes);d.save_area();assert window.db.get('scan_area_presets')['My area']['region']==[0,0,80,100]
    d.remove_area();assert window.db.get('scan_area_presets')=={};assert asset.read_bytes()==before

@pytest.mark.parametrize('value',[[],{'':{}},{'Bad':dict(device='x',source='y',region=[0,0,0,10])},{'Bad':dict(device='x',source='y',region=[0,0,float('nan'),10])}])
def test_invalid_scan_area_config_recovers_without_rewriting_raw_row(window,value):
    with pytest.raises(ValueError):validate_hardware_setting('scan_area_presets',value)
    raw=json.dumps(value);window.db.conn.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('scan_area_presets',raw));window.db.conn.commit()
    assert window.db.get('scan_area_presets',{})=={};assert window.db.conn.execute('SELECT value FROM config WHERE key=?',('scan_area_presets',)).fetchone()[0]==raw

def test_partial_preview_mapping_and_rectangular_handles(window,monkeypatch):
    d,_,_=scanner(window,monkeypatch);d.display_preview(Image.new('RGB',(600,400),'white'),[30,40,120,80])
    c=d.preview_canvas;drag(c,c.mapFromScene(QPointF(120,80)),c.mapFromScene(QPointF(360,240)))
    assert [b.value() for b in d.region]==pytest.approx([54,56,48,32],abs=1)
    item=c.outlines[0];item.corner_moved(0,QPointF(100,50));item.commit();p=item.region.points
    assert p[0][1]==p[1][1] and p[1][0]==p[2][0] and p[2][1]==p[3][1] and p[3][0]==p[0][0]

def test_preview_does_not_complete_pending_document_import(window,monkeypatch):
    d,_,calls=scanner(window,monkeypatch);completed=[];d.completion_callback=completed.append
    monkeypatch.setattr(window,'run',lambda fn,done,*args:done(fn()))
    d.scan_now(preview=True);path=d.folder/'original.bmp';Image.new('RGB',(230,330),'white').save(path)
    record=dict(width=230,height=330,format='BMP',original=str(path));d.verified(record)
    assert not completed and d.completion_callback is not None and d.preview_image is not None
    d.set_region([0,0,50,60]);d.scan_now();d.verified(record)
    assert completed==[record] and d.completion_callback is None

def test_changing_scanner_clears_preview_and_ignores_late_decode(window,monkeypatch):
    d,_,_=scanner(window,monkeypatch);old=d.area_context;im=Image.new('RGB',(230,330),'white');d.display_preview(im,[0,0,230,330],old)
    d.device.addItem('Other scanner','OTHER');d.device.setCurrentIndex(d.device.findData('OTHER'));d.device_changed()
    assert d.preview_image is None and not d.preview_canvas.has_image
    d.display_preview(im,[0,0,230,330],old);assert d.preview_image is None

def test_scan_draw_after_pan_zoom_and_view_rotation(window,monkeypatch):
    d,_,_=scanner(window,monkeypatch);d.display_preview(Image.new('RGB',(690,990),'white'),[0,0,230,330])
    d.pan_preview();assert d.preview_canvas.pan_mode and not d.preview_canvas.isInteractive()
    d.draw_area();c=d.preview_canvas;assert not c.pan_mode and c.isInteractive()
    c.rotate(90);c.scale(1.1,1.1)
    drag(c,c.mapFromScene(QPointF(138,198)),c.mapFromScene(QPointF(414,594)))
    assert [b.value() for b in d.region]==pytest.approx([46,66,92,132],abs=1.5)

def test_reference_dashboard_and_new_dark_default(window):
    w=window;assert w.property('themeMode')=='Dark' and not w.shell.hero.art.isNull()
    w.resize(1366,768);w.shell.resize(1366);QApplication.processEvents()
    assert len({card.y() for card in w.shell.action_cards})==1
    assert all(card.size().height()>=148 for card in w.shell.action_cards)
    assert [card.property('accent') for card in w.shell.action_cards]==['blue','green','purple','amber']
    hints=[label.text() for label in w.editor_tools.findChildren(QLabel)]
    assert any('Shift constrains' in text and 'Ctrl adds' in text for text in hints)
    assert not any('Shift adds' in text for text in hints)
    labels=[label.text() for label in w.shell.activity_card.findChildren(QLabel)]
    assert 'Quick Reprint' in labels and not any('Previous Order' in text for text in labels)
    w.shell.set_theme('Light');assert w.property('themeMode')=='Light'

@pytest.mark.parametrize('size',[(1050,740),(1366,768)])
def test_scan_settings_and_transform_tab_have_no_horizontal_clipping(window,monkeypatch,size):
    w=window;w.setFixedSize(*size);d,_,_=scanner(w,monkeypatch)
    for _ in range(8):QApplication.processEvents()
    assert d.device.geometry().right()<=d.device.parentWidget().size().width()
    d.advanced_settings.open_settings()
    for _ in range(8):QApplication.processEvents()
    assert d.area_presets.geometry().right()<=d.area_presets.parentWidget().size().width()
    d.advanced_settings.hide()
    w.start_workflow('portrait')
    w.photo_settings.open_settings()
    for _ in range(8):QApplication.processEvents()
    scroll=w.editor_tabs.widget(0)
    assert scroll.widget().size().width()<=scroll.viewport().size().width()
