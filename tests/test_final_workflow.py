import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import time
import pytest
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from app.services.cropping import CropTray,CropRegion
from app.models.domain import Photo,Layer,Job
from app.services.imaging import prepare_layer,render_photo
from app.services.framing import frame_photo
from app.ui.studio_window import StudioWindow

def wait(app,w):
    end=time.monotonic()+40
    while (w.busy or w.timer.isActive()) and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not w.busy and not w.timer.isActive()

def test_numbered_library_survives_restart_and_source_removal(tmp_path):
    root=tmp_path/'library';original=tmp_path/'camera.png';Image.new('RGB',(70,90),'red').save(original)
    tray=CropTray(root=root);source=tray.import_source(original);assert tray.import_source(original)==source;assert len(tray.sources())==1
    p1=tray.add('Alice',Image.new('RGB',(50,80),'blue'),source);p2=tray.add('Bob',Image.new('RGB',(60,90),'green'),source)
    assert (p1.serial,p2.serial)==(1,2);tray.rename(p1,'Alice edited');tray.save_regions(source,[CropRegion([(0,0),(20,0),(20,30),(0,30)])]);tray.remove({p2.id});tray.close();original.unlink()
    tray=CropTray(root=root);assert len(tray.items)==1;item=tray.items[0];assert item.serial==1 and item.name=='Alice edited';assert item._image is None;assert item.image.size==(50,80);assert Path(tray.sources()[0][2]).exists();assert len(tray.load_regions(source))==1
    p3=tray.add('Charlie',Image.new('RGB',(50,80),'white'));assert p3.serial==3;assert '#000003' in p3.display_name;tray.close()

def test_missing_library_asset_keeps_gallery_usable(tmp_path):
    tray=CropTray(root=tmp_path/'library');item=tray.add('Missing example',Image.new('RGB',(50,80),'white'));Path(item.asset).unlink();Path(item.thumb).unlink()
    assert item.thumbnail().width>0
    with pytest.raises(FileNotFoundError,match='Saved photo'):item.image
    tray.close()

def test_canvas_framing_reaches_bottom_and_preserves_head(tmp_path):
    path=tmp_path/'cutout.png';im=Image.new('RGBA',(400,600));d=ImageDraw.Draw(im);d.ellipse((130,70,280,260),fill='red');d.rectangle((100,230,320,590),fill='red');im.save(path)
    photo=Photo(layers=[Layer(str(path),str(path))]);frame_photo(photo);render=render_photo(photo,100);bg=(173,216,230)
    assert any(render.getpixel((x,render.height-1))!=bg for x in range(render.width))
    assert render.getpixel((render.width//2,0))==bg
    joint=Photo(width=55,height=45,kind='Joint composition',layers=[Layer(str(path),str(path)),Layer(str(path),str(path))]);frame_photo(joint);render=render_photo(joint,100)
    assert any(render.getpixel((x,render.height-1))!=bg for x in range(0,render.width//2))
    assert any(render.getpixel((x,render.height-1))!=bg for x in range(render.width//2,render.width))

def test_mask_brush_restores_original_and_adjustments_do_not_touch_source(tmp_path):
    path=tmp_path/'original.png';Image.new('RGB',(100,100),(100,60,20)).save(path);before=path.read_bytes();l=Layer(str(path),brightness=1.5)
    assert prepare_layer(l).getpixel((50,50))[0]==150
    l.mask_strokes=[dict(mode='erase',points=[[.5,.5]],radius=.2)];assert prepare_layer(l).getpixel((50,50))[3]==0
    l.mask_strokes.append(dict(mode='restore',points=[[.5,.5]],radius=.1));assert prepare_layer(l).getpixel((50,50))[3]==255
    assert path.read_bytes()==before
    j=Job(photos=[Photo(layers=[l])]);assert Job.from_dict(j.to_dict()).photos[0].layers[0].mask_strokes==l.mask_strokes

def test_transform_mouse_resize_rotate_and_redo(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda p,t,m:errors.append(m));monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Discard)
    path=tmp_path/'subject.png';Image.new('RGB',(500,600),'red').save(path);w.start_workflow('portrait');w.import_photos(paths=[str(path)]);wait(app,w)
    canvas=w.canvas;item=canvas.layers[0];old_x=w.layer().x;start=canvas.mapFromScene(item.pos());end=start+QPoint(25,10)
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(canvas.viewport(),end,20);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,end);wait(app,w);assert w.layer().x>old_x
    moved_x=w.layer().x;w.undo_edit();wait(app,w);assert w.layer().x==pytest.approx(old_x);w.redo_edit();wait(app,w);assert w.layer().x==pytest.approx(moved_x)
    item=canvas.layers[0];old_scale=w.layer().scale;handle=item.handles[0];start=canvas.mapFromScene(handle.scenePos());end=start+QPoint(-15,-15)
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(canvas.viewport(),end,20);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,end);wait(app,w);assert w.layer().scale>old_scale
    item=canvas.layers[0];handle=item.handles[-1];start=canvas.mapFromScene(handle.scenePos());end=start+QPoint(45,20)
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(canvas.viewport(),end,20);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,end);wait(app,w);assert abs(w.layer().rotation)>1
    canvas.set_tool('erase');center=canvas.mapFromScene(canvas.layers[0].pos());QTest.mouseClick(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,center);wait(app,w);assert w.layer().mask_strokes
    assert not errors;w.dirty=False;w.close();app.processEvents()

def test_combined_joint_and_saved_library_reload(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show()
    import app.ui.studio_window as module
    monkeypatch.setattr(module,'find_background_model',lambda p:tmp_path/'model.onnx');monkeypatch.setattr(module,'remove_background',lambda source,*a,**k:source)
    item=w.tray.add('Existing couple',Image.new('RGB',(600,400),'orange'));serial=item.serial;w.use_crops('joint',[item]);wait(app,w);assert len(w.photo.layers)==1 and w.photo.kind=='Combined joint';w.save_job();id=w.job.id;w.dirty=False;w.close();app.processEvents()
    w=StudioWindow();assert w.tray.items[0].serial==serial;assert w.db.load_job(id).photos[0].kind=='Combined joint';w.dirty=False;w.close();app.processEvents()

def test_joint_picker_keeps_checked_serials_across_searches(tmp_path):
    from app.ui.cropper import PreparedPicker
    app=QApplication.instance() or QApplication([]);tray=CropTray(root=tmp_path/'library');tray.add('Alice',Image.new('RGB',(20,30),'red'));tray.add('Bob',Image.new('RGB',(20,30),'blue'))
    picker=PreparedPicker(tray,(1,2));picker.search.setText('000001');assert picker.list.count()==1;picker.list.item(0).setCheckState(Qt.Checked)
    picker.search.setText('000002');picker.list.item(0).setCheckState(Qt.Checked);assert [p.serial for p in picker.chosen()]==[1,2];picker.accept();assert picker.result()==1;picker.close();tray.close()

@pytest.mark.parametrize('name,count',[('portrait (1).jpg',8),('portrait (2).jpg',9),('portrait (3).jpg',9)])
def test_supplied_tiled_print_sheets(name,count):
    from app.services.imaging import load_image
    from app.services.cropping import detect_photo_regions
    path=Path(__file__).resolve().parents[1]/'Demo'/name
    if not path.exists():pytest.skip('User demo fixtures are not present.')
    assert len(detect_photo_regions(load_image(path)))==count
