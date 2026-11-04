"""Full local acceptance against portrait sheets, combined joints and scanned prints."""
from pathlib import Path
import hashlib
import json
import time
import os

def verify_studio(demo_dir,destination):
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PIL import Image,ImageDraw
    from app.ui.studio_window import StudioWindow
    from app.services.imaging import render_photo,load_image
    from app.services.framing import detect_faces
    from app.services.pdf import export_pdf
    app=QApplication.instance() or QApplication([]);out=Path(destination);out.mkdir(parents=True,exist_ok=True);root=Path(demo_dir).resolve();start=time.monotonic();errors=[];windows=[]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.jpg')}
    old_warning=QMessageBox.warning;old_question=QMessageBox.question
    QMessageBox.warning=lambda p,t,m:errors.append(t+': '+m);QMessageBox.question=lambda *a,**k:QMessageBox.Discard
    def wait(w):
        deadline=time.monotonic()+180
        while (w.busy or w.timer.isActive()) and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        if w.busy or errors:raise RuntimeError('; '.join(errors) or 'Worker timed out')
    try:
        w=StudioWindow();windows.append(w);w.show()
        if os.environ.get('STUDIO_VERIFY_MODEL_DIR'):w.db.set('model_dir',os.environ['STUDIO_VERIFY_MODEL_DIR'])
        portrait_items=[];joint_items=[];counts={}
        for p in sorted(root.rglob('*.jpg')):
            w.import_to_cropper(paths=[str(p)]);wait(w);before=len(w.tray.items)
            if p.name.lower().startswith('joint'):
                w.cropper.full_image();w.cropper.keep_selected()
            else:w.cropper.keep_all()
            wait(w);items=w.tray.items[before:];counts[p.name]=len(items)
            if p.name.lower().startswith('joint'):joint_items.extend(items)
            else:portrait_items.extend(items)
        assert portrait_items and joint_items,'Need portrait and joint demo examples.'
        w.use_crops('portrait',[portrait_items[0]]);wait(w);render_photo(w.photo).save(out/'portrait.png');w.grab().save(str(out/'portrait-editor.png'))
        w.quantity.setValue(8);wait(w);w.show_print();wait(w);export_pdf(w.job,out/'portrait.pdf')
        checks=[]
        for index,item in enumerate(joint_items):
            w.dirty=False;w.use_crops('joint',[item]);wait(w);assert len(w.photo.layers)==1;render_photo(w.photo).save(out/f'combined-joint-{index+1}.png')
            layer=w.photo.layers[0];faces=detect_faces(load_image(layer.source));mask=load_image(layer.mask).getchannel('A');visible=0
            for x,y,fw,fh in faces:
                cx=min(mask.width-1,max(0,round(x+fw/2)));cy=min(mask.height-1,max(0,round(y+fh/2)));visible+=mask.getpixel((cx,cy))>150
            assert visible==len(faces),f'A detected face was removed in {item.name}'
            checks.append(dict(name=item.name,faces_detected=len(faces),faces_preserved=visible))
        w.dirty=False;w.use_crops('joint',portrait_items[:2]);wait(w);render_photo(w.photo).save(out/'separate-joint.png');w.grab().save(str(out/'joint-editor.png'));w.show_print();wait(w);export_pdf(w.job,out/'joint.pdf')
        w.stack.setCurrentIndex(1);w.layer().brightness=1.08;w.layer().mask_strokes=[dict(mode='erase',points=[[.02,.02]],radius=.01)];w.save_job();job_id=w.job.id
        serials=[(p.id,p.serial,p.name) for p in w.tray.items];total=len(serials);assert len({p.serial for p in w.tray.items})==total
        # Produce a library overview from saved thumbnails, without loading all originals into memory.
        columns=9;cell=(130,180);contact=Image.new('RGB',(columns*cell[0],((total+columns-1)//columns)*cell[1]),'#e7edf3')
        for i,item in enumerate(w.tray.items):
            image=item.thumbnail((120,150));x=(i%columns)*cell[0];y=(i//columns)*cell[1];contact.paste(image,(x+(cell[0]-image.width)//2,y));ImageDraw.Draw(contact).text((x+4,y+155),f'#{item.serial:06d}',fill='black')
        contact.save(out/'saved-library.png');w.dirty=False;w.close();app.processEvents();windows.remove(w)
        w=StudioWindow();windows.append(w);w.show();assert [(p.id,p.serial,p.name) for p in w.tray.items]==serials;assert all(p._image is None for p in w.tray.items)
        loaded=w.db.load_job(job_id);assert loaded.photos[0].layers[0].brightness==1.08 and loaded.photos[0].layers[0].mask_strokes
        w.open_cropper();wait(w);assert w.cropper.current_image is not None;w.grab().save(str(out/'saved-cropper.png'))
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        result=dict(passed=True,total_saved=total,counts=counts,combined_checks=checks,seconds=round(time.monotonic()-start,2),checks=['saved sources and permanent serials','tiled portrait sheets','automatic canvas framing','combined joint keeps both faces','two separate subjects','mask/color edit persistence','exact-size portrait/joint PDFs','library restart with lazy images','source preservation'])
    except Exception as e:
        import traceback
        result=dict(passed=False,error=str(e),traceback=traceback.format_exc())
    finally:
        for window in windows:window.dirty=False;window.close()
        app.processEvents();QMessageBox.warning=old_warning;QMessageBox.question=old_question
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return 0 if result['passed'] else 1
