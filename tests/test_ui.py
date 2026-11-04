import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import time
from PIL import Image
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow

def wait(app,window):
    deadline=time.monotonic()+30
    while (window.busy or window.preview_timer.isActive()) and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert not window.busy

def test_import_edit_save_preview(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);w=MainWindow();w.show()
    path=tmp_path/'person.png';Image.new('RGB',(900,1100),'orange').save(path)
    w.import_images(paths=[str(path)]);wait(app,w);assert len(w.job.photos)==1;assert not w.canvas.scene().items()==[]
    w.qty.setValue(8);w.width.setValue(45);w.height.setValue(55);wait(app,w);assert w.current_photo().quantity==8
    w.swap_size();wait(app,w);assert w.current_photo().width==55;w.undo_edit();wait(app,w);assert w.current_photo().width==45
    w.save_job();assert w.db.load_job(w.job.id).photos[0].quantity==8
    w.nav.setCurrentRow(4);wait(app,w);assert len(w.job.placements)==8;assert w.print_canvas.scene().items()
    for index in range(8):w.nav.setCurrentRow(index);wait(app,w)
    w.dirty=False;w.close();app.processEvents()
