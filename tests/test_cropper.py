import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QPointF
from app.services.cropping import CropRegion,CropTray,detect_photo_regions,extract_region
from app.services.imaging import load_image
from app.ui.studio_window import StudioWindow
from app.ui.cropper import PreparedPicker

def test_mouse_corner_adjustment_and_drawn_crop():
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt,QPoint
    from app.ui.cropper import CropCanvas
    app=QApplication.instance() or QApplication([]);canvas=CropCanvas();canvas.resize(650,650);region=CropRegion([(40,50),(230,50),(230,350),(40,350)]);canvas.display(Image.new('RGB',(500,700),'white'),[region]);canvas.show();app.processEvents()
    handle=canvas.outlines[0].handles[0];start=canvas.mapFromScene(handle.scenePos());end=start+QPoint(20,12)
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(canvas.viewport(),end,20);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,end);app.processEvents()
    assert region.points[0][0]>40 and region.points[0][1]>50
    drawn=[];canvas.drawn.connect(drawn.append);start=canvas.mapFromScene(QPointF(300,420));end=canvas.mapFromScene(QPointF(440,640))
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(canvas.viewport(),end,20);QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,Qt.NoModifier,end);app.processEvents()
    assert len(drawn)==1;assert drawn[0].points[0][0]==pytest.approx(300,abs=2);canvas.close()

def wait(app,w):
    end=time.monotonic()+30
    while (w.busy or w.timer.isActive()) and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not w.busy and not w.timer.isActive()

def test_multiple_prints_and_extraction():
    sheet=Image.new('RGB',(1000,1000),'white');d=ImageDraw.Draw(sheet)
    d.rectangle((70,100,350,520),fill='#aa3240',outline='black',width=3);d.rectangle((610,400,900,840),fill='#2244aa',outline='black',width=3)
    regions=detect_photo_regions(sheet);assert len(regions)==2
    colors=[]
    for r in regions:
        crop=extract_region(sheet,r);assert crop.width<450 and crop.height<550;colors.append(crop.getpixel((crop.width//2,crop.height//2)))
    assert (170,50,64) in colors and (34,68,170) in colors

def test_perspective_corners_and_manual_rotation():
    image=Image.new('RGB',(300,400),'white');ImageDraw.Draw(image).rectangle((40,50,240,350),fill='red')
    region=CropRegion([(40,50),(240,50),(240,350),(40,350)]);crop=extract_region(image,region);assert crop.size==(200,300);assert crop.getpixel((100,150))==(255,0,0)
    region.rotation=90;assert extract_region(image,region).size==(300,200)

def test_phone_exif_and_original_preservation(tmp_path):
    path=tmp_path/'camera.jpg';image=Image.new('RGB',(600,400),'blue');exif=Image.Exif();exif[274]=6;image.save(path,exif=exif)
    before=path.read_bytes();loaded=load_image(path,10000);assert loaded.size==(400,600)
    extract_region(loaded,CropRegion([(0,0),(399,0),(399,599),(0,599)]));assert path.read_bytes()==before

def test_memory_tray_and_durable_selected_assets(tmp_path):
    tray=CropTray(max_pixels=1000);item=tray.add('Person',Image.new('RGB',(20,30),'red'))
    assert not item.asset and list(tmp_path.iterdir())==[]
    path=tray.materialize(item,tmp_path/'jobs');assert Path(path).exists();assert tray.materialize(item,tmp_path/'jobs')==path
    with pytest.raises(ValueError,match='full'):tray.add('Too many',Image.new('RGB',(30,30)))
    tray.remove({item.id});assert not tray.items;assert Path(path).exists(),'Saved-job assets must survive tray removal.'

def test_cropper_to_makers_session_flow(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda p,t,m:errors.append(m));monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Discard)
    scan=Image.new('RGB',(1000,1000),'white');d=ImageDraw.Draw(scan);d.rectangle((80,100,350,500),fill='red',outline='black',width=3);d.rectangle((620,400,900,820),fill='blue',outline='black',width=3);source=tmp_path/'sheet.jpg';scan.save(source)
    w.import_to_cropper(paths=[str(source)]);wait(app,w);assert w.stack.currentIndex()==3;assert len(w.cropper.regions)==2
    outline=w.cropper.canvas.outlines[0];before=w.cropper.regions[0].points[0];handle=outline.handles[0];handle.setPos(handle.pos()+QPointF(10,10));outline.commit();assert w.cropper.regions[0].points[0]!=before
    w.cropper.keep_all();wait(app,w);assert len(w.tray.items)==2;assert all(Path(p.asset).exists() for p in w.tray.items)
    images=list(w.tray.items)
    import app.ui.studio_window as module
    seen=[];monkeypatch.setattr(module,'find_background_model',lambda p:tmp_path/'model.onnx')
    def remove(source,*a,**k):
        with Image.open(source) as im:seen.append(im.size)
        return source
    monkeypatch.setattr(module,'remove_background',remove)
    w.use_crops('portrait',[images[0]]);wait(app,w);assert len(w.photo.layers)==1;assert seen[0]!=scan.size;assert w.photo.layers[0].source!=str(source)
    assert len(w.tray.items)==2;w.open_cropper();assert len(w.tray.items)==2
    w.dirty=False;w.use_crops('joint',images);wait(app,w);assert len(w.photo.layers)==2;assert all(l.mask for l in w.photo.layers);assert len(w.tray.items)==2
    picker=PreparedPicker(w.tray,2,w);picker.accept();assert picker.error.text();picker.list.item(0).setSelected(True);picker.list.item(1).setSelected(True);assert len(picker.chosen())==2;picker.accept();assert picker.result()==1
    assert not errors;w.dirty=False;w.close();app.processEvents()
