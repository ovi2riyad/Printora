"""Exercise the actual asynchronous UI with a local frontal-face fixture."""
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from app.ui.main_window import MainWindow

def main():
    app=QApplication.instance() or QApplication([]);window=MainWindow();window.show();errors=[]
    QMessageBox.warning=lambda parent,title,message:errors.append(title+': '+message)
    QMessageBox.question=lambda *a,**k:QMessageBox.Yes
    source=str(Path('.tools/face-test.jpg').resolve());output=Path('.tools/ui-acceptance.pdf').resolve()
    def wait():
        end=time.monotonic()+90
        while (window.busy or window.preview_timer.isActive()) and time.monotonic()<end:
            app.processEvents();time.sleep(.01)
        assert not window.busy,'Worker timed out'
        assert not errors,'\n'.join(errors)
    window.import_images(paths=[source]);wait();window.nav.setCurrentRow(2)
    window.remove_bg();wait();assert window.current_layer().mask
    window.auto_face();wait();window.qty.setValue(8);window.move_layer(.01,.01);wait()
    assert window.current_photo().quantity==8
    QFileDialog.getOpenFileNames=lambda *a,**k:([source,source],'')
    window.create_joint();wait();assert len(window.current_photo().layers)==2
    window.qty.setValue(2);window.layer_choice.setCurrentIndex(1);window.move_layer(.03,0);wait()
    window.import_images(paths=[source],combined=True);wait();window.select_photo(2);window.qty.setValue(2);window.width.setValue(60);window.height.setValue(40);wait()
    window.import_images(paths=[source]);wait();window.select_photo(3);window.qty.setValue(2);window.width.setValue(35);window.height.setValue(45);wait()
    window.job.name='Local acceptance validation';window.nav.setCurrentRow(4);wait();assert len(window.job.placements)==14
    window.open_folder.setChecked(False);QFileDialog.getSaveFileName=lambda *a,**k:(str(output),'')
    window.export();wait();assert output.exists()
    id=window.job.id;window.save_job();loaded=window.db.load_job(id);assert len(loaded.photos)==4;assert len(loaded.photos[1].layers)==2;assert len(loaded.placements)==14
    window.grab().save('.tools/composer-windows.png');window.nav.setCurrentRow(2);wait();window.select_photo(1);wait();window.grab().save('.tools/editor-windows.png')
    # Diagnostic order is deliberately not kept in the operator's history.
    with window.db.conn:
        window.db.conn.execute('DELETE FROM jobs WHERE id=?',(id,));window.db.conn.execute('DELETE FROM exports WHERE path=?',(str(output),))
    window.dirty=False;window.close();app.processEvents();print('PASS: actual UI portrait masking/face/crop, joint layers, four mixed items, PDF export and editable job reload')

if __name__=='__main__':main()
