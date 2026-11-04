"""Standalone-package verification of real scan-to-crop-to-maker processing."""
from pathlib import Path
import hashlib
import json
import time

def verify_cropper(source,destination):
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PIL import Image
    from app.ui.studio_window import StudioWindow
    from app.services.pdf import export_pdf
    app=QApplication.instance() or QApplication([]);out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    source=Path(source).resolve();initial=hashlib.sha256(source.read_bytes()).hexdigest();errors=[];start=time.monotonic();w=StudioWindow();w.show()
    old_warning=QMessageBox.warning;old_question=QMessageBox.question
    QMessageBox.warning=lambda p,t,m:errors.append(t+': '+m)
    QMessageBox.question=lambda *a,**k:QMessageBox.Discard
    def wait():
        deadline=time.monotonic()+120
        while (w.busy or w.timer.isActive()) and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        if w.busy or errors:raise RuntimeError('; '.join(errors) or 'Worker timed out.')
    try:
        w.import_to_cropper(paths=[str(source)]);wait();count=len(w.cropper.regions)
        if count<2:raise ValueError('Use a scan sheet containing at least two separate prints.')
        before=len(w.tray.items);w.cropper.keep_all();wait();assert len(w.tray.items)==before+count;assert all(Path(p.asset).exists() for p in w.tray.items)
        w.grab().save(str(out/'cropper.png'));items=list(w.tray.items)
        w.use_crops('portrait',[items[0]]);wait();assert w.photo.layers[0].mask;w.grab().save(str(out/'portrait.png'))
        w.dirty=False;w.use_crops('joint',items[:2]);wait();assert len(w.photo.layers)==2
        for layer in w.photo.layers:
            assert layer.source!=str(source)
            with Image.open(layer.mask) as image:assert image.getchannel('A').getextrema()==(0,255)
        w.grab().save(str(out/'joint.png'));w.show_print();wait();export_pdf(w.job,out/'joint.pdf')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==initial
        result=dict(passed=True,crops=count,seconds=round(time.monotonic()-start,2),checks=['multi-photo scan detection','perspective crop extraction','memory tray','portrait selection','two-person selection','automatic CPU background removal','PDF export','source preservation'])
    except Exception as e:
        import traceback
        result=dict(passed=False,error=str(e),traceback=traceback.format_exc())
    finally:
        w.dirty=False;w.close();app.processEvents();QMessageBox.warning=old_warning;QMessageBox.question=old_question
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return 0 if result['passed'] else 1
