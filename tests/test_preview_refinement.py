"""Large previews, durable processing and bounded pre-acquisition scanner retries."""
import hashlib,time
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from app.models.domain import Photo,Layer,Job
from app.services.imaging import prepare_layer,render_photo


def settle(w):
    end=time.monotonic()+25
    while (w.busy or w.timer.isActive()) and time.monotonic()<end:
        QApplication.processEvents();time.sleep(.01)
    assert not w.busy
    for _ in range(8):QApplication.processEvents()


@pytest.fixture
def window(tmp_path,monkeypatch):
    from app.services import user_folders
    from app.ui.hardware_process import HardwareProcess
    from app.ui.studio_window import StudioWindow
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'data'))
    monkeypatch.setattr(user_folders,'documents_directory',lambda:tmp_path/'Documents')
    monkeypatch.setattr(HardwareProcess,'start',lambda *a:None)
    app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();app.processEvents()
    yield w
    w.timer.stop();w.pool.waitForDone();app.processEvents();w.invalidate_autosave();w.dirty=False
    for doc in (w.shell.copy,w.shell.nid):
        if doc.preview_dialog:doc.preview_dialog.close()
        doc.dirty=False
    w.photo_settings.hide();w.hardware.shutdown();w.close();w.deleteLater();app.processEvents()


@pytest.fixture
def textured_photo(tmp_path):
    rng=np.random.default_rng(1234);rgb=np.clip(np.array([190,145,120])+rng.normal(0,9,(240,220,3)),0,255).astype('uint8')
    im=Image.fromarray(rgb).convert('RGBA');alpha=Image.new('L',im.size,220);im.putalpha(alpha)
    path=tmp_path/'original.png';im.save(path);return path


def test_skin_softening_is_face_local_reversible_and_keeps_original_alpha(textured_photo,monkeypatch):
    from app.services import framing
    monkeypatch.setattr(framing,'detect_faces',lambda image:[(20,20,160,190)])
    path=textured_photo;digest=hashlib.sha256(path.read_bytes()).digest();layer=Layer(str(path))
    baseline=prepare_layer(layer);layer.skin_soften=.8;soft=prepare_layer(layer)
    a,b=np.asarray(baseline),np.asarray(soft)
    assert np.array_equal(a[:,:,3],b[:,:,3])
    assert np.array_equal(a[:20],b[:20]) and np.array_equal(a[:,190:],b[:,190:])
    assert np.array_equal(a[65:90,70:120],b[65:90,70:120])  # protected eyes/brows
    assert not np.array_equal(a[120:140,50:65,:3],b[120:140,50:65,:3])
    layer.skin_soften=0;assert prepare_layer(layer).tobytes()==baseline.tobytes()
    assert hashlib.sha256(path.read_bytes()).digest()==digest


def test_processing_serialization_and_export_use_the_same_pixels(textured_photo,tmp_path):
    from app.services.imaging import export_photo_image
    layer=Layer(str(textured_photo),denoise=.7,shadows=.35,temperature=-.3)
    photo=Photo(width=42,height=52,layers=[layer],border=False)
    baseline=render_photo(Photo(width=42,height=52,layers=[Layer(str(textured_photo))],border=False))
    restored=Job.from_dict(Job(photos=[photo]).to_dict()).photos[0]
    actual=render_photo(restored);assert actual.tobytes()!=baseline.tobytes()
    path=tmp_path/'finished.png';export_photo_image(restored,str(path))
    with Image.open(path) as exported:assert exported.convert('RGB').tobytes()==actual.tobytes()
    old=Job(photos=[Photo(layers=[Layer(str(textured_photo))])]).to_dict()
    for key in ('denoise','shadows','temperature','skin_soften'):del old['photos'][0]['layers'][0][key]
    legacy=Job.from_dict(old).photos[0].layers[0]
    assert legacy.denoise==legacy.shadows==legacy.temperature==legacy.skin_soften==0


@pytest.mark.parametrize('key,value',[('denoise',float('nan')),('skin_soften',2),('shadows','0.2'),('temperature',-2)])
def test_bad_processing_settings_fail_at_document_boundary(key,value):
    data=Job(photos=[Photo(layers=[Layer('not-loaded.png')])]).to_dict();data['photos'][0]['layers'][0][key]=value
    with pytest.raises(ValueError,match='processing'):Job.from_dict(data)


@pytest.mark.parametrize('mode',['portrait','joint','nid'])
@pytest.mark.parametrize('size',[(1366,720),(1280,680)])
def test_main_workspaces_fit_without_outer_scrolling(window,mode,size):
    w=window;w.resize(*size)
    if mode=='nid':w.shell.open(w.shell.nid)
    else:w.start_workflow(mode)
    settle(w);scroll=w.shell.workspace_scroll
    assert scroll.horizontalScrollBar().maximum()==0
    assert scroll.verticalScrollBar().maximum()==0
    if mode!='nid':
        assert w.canvas.viewport().height()>=300
        assert w.floating_tabs.tabText(0)=='Image Processing' and w.denoise.isVisible()
        width=w.canvas.viewport().width();w.editor_panel.set_mode('icons');settle(w)
        assert w.canvas.viewport().width()==width and w.editor_panel.width()==52
        w.editor_panel.set_mode('small');settle(w)
        assert w.editor_panel.width()<=280 and w.denoise.isVisible()


def test_editor_action_row_colors_softener_and_undo(window,textured_photo):
    w=window;w.start_workflow('portrait');w.photo.layers=[Layer(str(textured_photo),label='Client portrait')];w.sync_controls();settle(w)
    assert 'Client portrait' in w.subject.currentText() and str(textured_photo) not in w.subject.currentText()
    page=w.stack.currentWidget();names=['Add photos to session','Create order','Preview PDF']
    actions=[next(b for b in page.findChildren(QPushButton) if (b.accessibleName() or b.text())==name) for name in names]+[w.photo_settings_button]
    assert all(button.isVisible() for button in actions)
    assert len({button.mapTo(page,QPoint()).y() for button in actions})==1
    w.background_swatches[1][0].click();assert w.photo.background=='#FFFFFF'
    settle(w);w.auto_soften.click();assert w.photo.layers[0].skin_soften>0
    settle(w);w.auto_soften.click();assert w.photo.layers[0].skin_soften==0
    w.undo_edit();assert w.photo.layers[0].skin_soften>0 and w.auto_soften.isChecked()


def test_crop_button_saves_all_and_opens_the_library(window,tmp_path):
    from app.services.cropping import CropRegion
    w=window;source=tmp_path/'sheet.png';Image.new('RGB',(400,300),'#c6aa8c').save(source);original=source.read_bytes()
    w.open_cropper(load_source=False);c=w.cropper;c.current_path=w.tray.import_source(source);c.current_image=Image.open(source).convert('RGBA')
    c.regions=[CropRegion([(10,10),(180,10),(180,280),(10,280)]),CropRegion([(210,10),(390,10),(390,280),(210,280)])];c.refresh_regions();settle(w)
    assert c.side_tabs.tabBar().isHidden() and c.crop_button.text()=='Crop' and c.crop_button.objectName()=='primary'
    assert c.region_list.count()==2 and all(not c.region_list.item(i).text() and not c.region_list.item(i).icon().isNull() for i in range(2))
    c.set_thumb_size(104);assert c.region_list.iconSize().width()==104
    QTest.mouseClick(c.crop_button,Qt.LeftButton);settle(w)
    assert w.stack.currentWidget() is w.studio.library and len(w.tray.items)==2
    assert source.read_bytes()==original and len({p.serial for p in w.tray.items})==2


def test_scanner_fallback_prioritizes_family_then_skips_failed_interfaces(window,tmp_path,monkeypatch):
    w=window;hub=w.hardware;d=hub.scan_dialog;requests=[]
    devices=[dict(id='wia-a',name='Brother Test (WIA)',backend='wia'),dict(id='wia-b',name='Other scanner',backend='wia'),dict(id='twain32:a',name='Brother Test (TWAIN32)',backend='twain32')]
    hub.scanners=devices;d.update_devices()
    caps=dict(sources=[dict(id='bed',name='Flatbed',width_mm=210,height_mm=297,resolutions=[150,300],colors=['color','gray'])],status='Test')
    d.result('capabilities',caps)
    monkeypatch.setattr(hub.scan_process,'start',lambda backend,request,*args:requests.append((backend,request)))
    d.set_region([12,15,60,80]);d.scan_now();original=dict(hub.scan_request)
    hub.scanner_error('WIA failed before transfer');assert requests[-1][1]['device']=='twain32:a' and requests[-1][1]['action']=='capabilities'
    hub.scanner_error('TWAIN cannot connect');assert requests[-1][1]['device']=='wia-b'
    d.result('capabilities',caps);assert requests[-1][1]['action']=='scan'
    for key in ('dpi','color','region','max_pages'):assert requests[-1][1][key]==original[key]
    before=len(requests);(d.folder/'acquisition.started').touch();hub.scanner_error('Failure after transfer began')
    assert len(requests)==before and d.folder.exists()
    d.scan_now(preview=True);hub.scanner_error('Preview interface failed before transfer')
    alternate=dict(sources=[dict(caps['sources'][0],resolutions=[75,300])],status='Alternate preview')
    d.result('capabilities',alternate)
    assert d.acquisition_preview and requests[-1][1]['action']=='scan' and requests[-1][1]['dpi']==75
    assert d.dpi.currentData()==300 and requests[-1][1]['region']==[0,0,210,297]


def test_scanner_cancel_never_starts_an_alternative(window,tmp_path,monkeypatch):
    hub=window.hardware;d=hub.scan_dialog;hub.scanners=[dict(id='a',name='A'),dict(id='b',name='B')];d.update_devices()
    hub.scan_action='capabilities';d.pending_scan=True;d.cancel();calls=[];monkeypatch.setattr(d,'connect_device',lambda:calls.append(1))
    hub.scanner_error('Driver closed after cancellation');assert not calls and not d.pending_scan


def test_removed_library_recovery_retains_identity_and_assets(window,monkeypatch):
    from PySide6.QtWidgets import QDialog
    from app.ui.photo_library import PhotoLibrary
    w=window;photo=w.tray.add('Recover me',Image.new('RGB',(90,120),'#c39773'),'source')
    path=Path(photo.asset);original=path.read_bytes();w.tray.remove({photo.id})
    def restore_through_dialog(dialog):
        gallery=dialog.findChild(PhotoLibrary);item=gallery.list.item(0);item.setCheckState(Qt.Checked)
        assert gallery.chosen()[0].serial==photo.serial and '1 selected' in gallery.selection.text()
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Restore selected').click()
        return 0
    monkeypatch.setattr(QDialog,'exec',restore_through_dialog);w.studio.library.restore_removed()
    assert w.tray.by_ids({photo.id})[0].serial==photo.serial and path.read_bytes()==original
