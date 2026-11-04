"""Actual demo-sheet + in-memory tray + CPU removal acceptance check."""
import json
import time
from pathlib import Path
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication,QMessageBox
from app.ui.studio_window import StudioWindow
from app.services.imaging import render_photo

def main():
    app=QApplication.instance() or QApplication([]);w=StudioWindow();w.show();errors=[];results={};start=time.monotonic()
    QMessageBox.warning=lambda p,t,m:errors.append(t+': '+m)
    QMessageBox.question=lambda *a,**k:QMessageBox.Discard
    def wait():
        deadline=time.monotonic()+120
        while (w.busy or w.timer.isActive()) and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        assert not w.busy and not errors,str(errors)
    paths=sorted(Path('Demo/Pictures').glob('*.jpg'));assert paths,'No demo scan sheets found.'
    for path in paths:
        before=len(w.tray.items);w.import_to_cropper(paths=[str(path.resolve())]);wait();regions=len(w.cropper.regions);w.cropper.keep_all();wait();assert len(w.tray.items)==before+regions
        results[path.name]=regions
    assert sum(results.values())>=30,results
    assert all(not p.asset for p in w.tray.items),'Crops should still be in memory before use.'
    thumb_w,thumb_h=150,210;columns=9;rows=(len(w.tray.items)+columns-1)//columns;contact=Image.new('RGB',(columns*thumb_w,rows*thumb_h),'#e6ecf2')
    for i,p in enumerate(w.tray.items):
        im=p.image.copy();im.thumbnail((thumb_w-10,thumb_h-25));x=(i%columns)*thumb_w;y=(i//columns)*thumb_h;contact.paste(im,(x+(thumb_w-im.width)//2,y));ImageDraw.Draw(contact).text((x+5,y+thumb_h-20),str(i+1),fill='black')
    contact.save('.tools/demo-crops-contact.png');w.grab().save('.tools/cropper-sheets.png')
    items=list(w.tray.items);w.use_crops('portrait',[items[0]]);wait();assert w.photo.layers[0].mask
    portrait=render_photo(w.photo);portrait.save('.tools/demo-crop-portrait.png');w.grab().save('.tools/cropper-portrait.png')
    w.dirty=False;w.use_crops('joint',[items[0],items[1]]);wait();assert all(l.mask for l in w.photo.layers);render_photo(w.photo).save('.tools/demo-crop-joint.png')
    w.grab().save('.tools/cropper-joint.png');w.show_print();wait()
    from app.services.pdf import export_pdf
    export_pdf(w.job,'.tools/demo-cropped-joint.pdf');w.save_job();saved=w.db.load_job(w.job.id);assert all(Path(l.source).exists() and Path(l.mask).exists() for l in saved.photos[0].layers)
    with w.db.conn:w.db.conn.execute('DELETE FROM jobs WHERE id=?',(w.job.id,))
    results['tray_total']=len(w.tray.items);results['seconds']=round(time.monotonic()-start,2);results['passed']=True;Path('.tools/cropper-result.json').write_text(json.dumps(results,indent=2));w.dirty=False;w.close();app.processEvents();print(json.dumps(results))

if __name__=='__main__':main()
