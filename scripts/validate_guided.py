"""Exercise the simplified UI against actual local CPU inference."""
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog
from PySide6.QtGui import QDesktopServices
from PIL import Image
from pypdf import PdfReader
from app.ui.studio_window import StudioWindow

def main():
    app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();errors=[]
    QMessageBox.warning=lambda p,t,m:errors.append(t+': '+m)
    QMessageBox.question=lambda *a,**k:QMessageBox.Yes
    QDesktopServices.openUrl=lambda *a:True
    source=str(Path('.tools/face-test.jpg').resolve())
    def wait():
        limit=time.monotonic()+90
        while (w.busy or w.timer.isActive()) and time.monotonic()<limit:
            app.processEvents();time.sleep(.01)
        assert not w.busy and not errors,str(errors)
    w.start_workflow('portrait');w.import_photos(paths=[source]);wait()
    assert w.photo.layers[0].scale!=1,'Auto-crop did not run'
    w.grab().save('.tools/guided-crop.png')
    w.remove_backgrounds();wait();assert w.photo.layers[0].mask
    with Image.open(w.photo.layers[0].mask) as im:assert im.getchannel('A').getextrema()==(0,255)
    w.quantity.setValue(8);wait();w.grab().save('.tools/guided-portrait.png');w.show_print();wait()
    output=str(Path('.tools/guided-portrait.pdf').resolve());QFileDialog.getSaveFileName=lambda *a,**k:(output,'');w.print_pdf();wait();assert len(PdfReader(output).pages)==1
    w.grab().save('.tools/guided-sheet.png');portrait_id=w.job.id;w.dirty=False;w.start_workflow('joint');w.import_photos(paths=[source,source]);wait();w.remove_backgrounds();wait();w.grab().save('.tools/guided-joint.png');assert all(l.mask for l in w.photo.layers)
    assert w.canvas.guide_count==2
    with w.db.conn:
        w.db.conn.execute('DELETE FROM jobs WHERE id=?',(portrait_id,));w.db.conn.execute('DELETE FROM exports WHERE path=?',(output,))
    w.dirty=False;w.close();app.processEvents();print('PASS: guided auto-crop, real CPU background removal, portrait/joint guides, tight PDF and UI screenshots')

if __name__=='__main__':main()
