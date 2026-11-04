import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
from pathlib import Path
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog
from app.ui.studio_window import StudioWindow
from app.services.layout import auto_layout
from app.models.domain import Photo

def wait(app,w):
    end=time.monotonic()+40
    while (w.busy or w.timer.isActive()) and time.monotonic()<end:
        app.processEvents();time.sleep(.01)
    assert not w.busy and not w.timer.isActive()

def test_guided_portrait_and_joint(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda parent,title,message:errors.append(message))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Discard)
    w.start_workflow('portrait');assert (w.width.value(),w.height.value())==(45,55);assert w.photo.background=='#ADD8E6';assert w.canvas.guide_count==1
    source=tmp_path/'person.png';Image.new('RGB',(600,800),'orange').save(source)
    w.import_photos(paths=[str(source)]);wait(app,w);assert len(w.photo.layers)==1;assert 'no face' in w.crop_hint.text()
    # Exercise the processing button and resulting color preview through the real worker.
    mask=tmp_path/'mask.png';im=Image.new('RGBA',(600,800),(0,0,0,0));from PIL import ImageDraw
    ImageDraw.Draw(im).ellipse((100,100,500,799),fill='orange');im.save(mask)
    import app.ui.studio_window as module
    monkeypatch.setattr(module,'find_background_model',lambda path:tmp_path/'fake.onnx')
    monkeypatch.setattr(module,'remove_background',lambda *a,**k:str(mask))
    w.remove_backgrounds();wait(app,w);assert w.photo.layers[0].mask==str(mask);assert 'Background removed' in w.background_status.text();assert not w.before.isChecked()
    w.quantity.setValue(8);wait(app,w);w.show_print();wait(app,w);assert len(w.job.placements)==8;assert w.job.placements[1].x-w.job.placements[0].x==45.2
    assert w.job.placements[4].y-w.job.placements[0].y==55.2
    w.stack.setCurrentIndex(1);w.paper.setCurrentIndex(1);assert '6 photos' in w.capacity.text()
    w.dirty=False;w.start_workflow('joint');assert (w.photo.width,w.photo.height)==(55,45);assert w.canvas.guide_count==2
    w.import_photos(paths=[str(source),str(source)]);wait(app,w);assert len(w.photo.layers)==2
    w.subject.setCurrentIndex(1);w.move_subject(.05,0);wait(app,w);assert w.photo.layers[1].x>w.photo.layers[0].x
    assert not errors;w.dirty=False;w.close();app.processEvents()

def test_tight_layout_capacity():
    settings=dict(margin=10,gap_x=.2,gap_y=.2,landscape=False)
    rows=auto_layout([Photo(quantity=10)],settings);assert sum(r.y==10 for r in rows)==4
    rows=auto_layout([Photo(width=35,height=45,quantity=10)],settings);assert sum(r.y==10 for r in rows)==5
    settings['landscape']=True;rows=auto_layout([Photo(quantity=12)],settings);assert sum(r.y==10 for r in rows)==6
