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
    from app.services.imaging import export_photo_image,remove_background
    from app.services.layout import validate_layout,layout_capacity
    from app.services.storage import backup_data,prepare_restore,install_restore
    from app.services.cropping import CropTray
    from app.core.database import data_root,Database
    from app.ui.studio_settings import StudioSettings
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
        # Exercise the new layouts through their actual controls, preserving existing copies.
        w.sheet_options.layout.setCurrentIndex(w.sheet_options.layout.findData('grid_2x2'));wait(w)
        coordinates={r.copy:(r.x,r.y,r.page) for r in w.job.placements}
        w.change_quantity(2);wait(w);assert w.photo.quantity==10 and w.job.page_count==3
        assert all((r.x,r.y,r.page)==coordinates[r.copy] for r in w.job.placements if r.copy<8)
        validate_layout(w.job);export_pdf(w.job,out/'portrait-2x2.pdf');w.grab().save(str(out/'print-2x2.png'))
        w.sheet_options.columns.setValue(3);w.sheet_options.rows.setValue(2);w.sheet_options.layout.setCurrentIndex(w.sheet_options.layout.findData('custom'));w.quantity.setValue(14);wait(w)
        assert w.job.page_count==3;validate_layout(w.job);export_pdf(w.job,out/'portrait-custom-grid.pdf')
        w.sheet_options.layout.setCurrentIndex(w.sheet_options.layout.findData('max_fit'));w.sheet_options.paper.setCurrentIndex(1);w.quantity.setValue(24);wait(w)
        assert layout_capacity(w.photo,w.job.print_settings)==(6,3);assert w.job.page_count==2
        w.stack.setCurrentIndex(1);before_layers=[vars(layer).copy() for layer in w.photo.layers]
        w.profile_picker.setCurrentText('Bangladesh Studio Portrait');w.apply_selected_profile();wait(w)
        assert [vars(layer) for layer in w.photo.layers]==before_layers
        w.set_color('border_color','#786b85');w.border_mm.setValue(.35);wait(w)
        w.run(lambda:export_photo_image(w.photo,out/'profile-portrait.png'),lambda _:None);wait(w)
        w.db.set('processing_quality','fine');w.remove_backgrounds();wait(w);w.db.set('processing_quality','balanced')
        assert Path(w.photo.layers[0].mask).exists()
        w.open_cropper();wait(w);rotation=w.cropper.regions[0].rotation
        w.cropper.rotate(90);w.undo_edit();assert w.cropper.regions[0].rotation==rotation;w.redo_edit();w.undo_edit()
        recover=portrait_items[-1];w.tray.remove({recover.id});assert any(p.id==recover.id for p in w.tray.query(deleted=True))
        w.tray.restore_items({recover.id});assert next(p for p in w.tray.items if p.id==recover.id).serial==recover.serial
        w.cropper.refresh_tray();w.cropper.side_tabs.setCurrentIndex(1);w.grab().save(str(out/'library-browser.png'))
        w.settings_dialog();app.processEvents();preferences=w.dialog.findChild(StudioSettings);preferences.tabs.setCurrentIndex(2);app.processEvents();w.dialog.grab().save(str(out/'print-settings.png'));w.dialog.close()
        checks=[]
        for index,item in enumerate(joint_items):
            w.dirty=False;w.use_crops('joint',[item]);wait(w);assert len(w.photo.layers)==1;render_photo(w.photo).save(out/f'combined-joint-{index+1}.png')
            layer=w.photo.layers[0];faces=detect_faces(load_image(layer.source));mask=load_image(layer.mask).getchannel('A');visible=0
            for x,y,fw,fh in faces:
                cx=min(mask.width-1,max(0,round(x+fw/2)));cy=min(mask.height-1,max(0,round(y+fh/2)));visible+=mask.getpixel((cx,cy))>150
            assert visible==len(faces),f'A detected face was removed in {item.name}'
            checks.append(dict(name=item.name,faces_detected=len(faces),faces_preserved=visible))
        w.dirty=False;w.use_crops('joint',portrait_items[:2]);wait(w);render_photo(w.photo).save(out/'separate-joint.png');w.grab().save(str(out/'joint-editor.png'));w.show_print();wait(w);export_pdf(w.job,out/'joint.pdf')
        w.stack.setCurrentIndex(1);w.layer().brightness=1.08;w.layer().defringe=.2;w.layer().mask_strokes=[dict(mode='erase',points=[[.02,.02]],radius=.01)];w.save_job();job_id=w.job.id
        w.db.set('quantity',6);w.db.set('layout','grid_2x2')
        backup=out/'studio-backup.zip';restored_root=data_root().with_name('StudioPhotoMaker-restored-check');stage=[]
        w.run(lambda:backup_data(data_root(),backup),lambda _:None);wait(w)
        w.run(lambda:prepare_restore(backup,restored_root),lambda result:stage.append(result));wait(w)
        install_restore(stage[0],restored_root)
        restored_db=Database(restored_root/'studio.db');restored_job=restored_db.load_job(job_id)
        assert restored_db.get('quantity')==6 and all(Path(layer.source).is_file() and Path(layer.mask).is_file() for layer in restored_job.photos[0].layers);restored_db.conn.close()
        restored_library=CropTray(root=restored_root/'library');assert len(restored_library.items)==len(w.tray.items);restored_library.close()
        serials=[(p.id,p.serial,p.name) for p in w.tray.items];total=len(serials);assert len({p.serial for p in w.tray.items})==total
        # Produce a library overview from saved thumbnails, without loading all originals into memory.
        columns=9;cell=(130,180);contact=Image.new('RGB',(columns*cell[0],((total+columns-1)//columns)*cell[1]),'#e7edf3')
        for i,item in enumerate(w.tray.items):
            image=item.thumbnail((120,150));x=(i%columns)*cell[0];y=(i//columns)*cell[1];contact.paste(image,(x+(cell[0]-image.width)//2,y));ImageDraw.Draw(contact).text((x+4,y+155),f'#{item.serial:06d}',fill='black')
        contact.save(out/'saved-library.png');w.dirty=False;w.close();app.processEvents();windows.remove(w)
        w=StudioWindow();windows.append(w);w.show();assert [(p.id,p.serial,p.name) for p in w.tray.items]==serials;assert all(p._image is None for p in w.tray.items)
        loaded=w.db.load_job(job_id);assert loaded.photos[0].layers[0].brightness==1.08 and loaded.photos[0].layers[0].mask_strokes and loaded.photos[0].layers[0].defringe==.2
        w.start_workflow('portrait');assert w.photo.quantity==6 and w.job.print_settings['layout']=='grid_2x2';w.dirty=False
        w.open_cropper();wait(w);assert w.cropper.current_image is not None;w.grab().save(str(out/'saved-cropper.png'))
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        result=dict(passed=True,total_saved=total,counts=counts,combined_checks=checks,seconds=round(time.monotonic()-start,2),checks=['saved sources and permanent serials','tiled portrait sheets','automatic canvas framing','combined joint keeps both faces','two separate subjects','mask/color/halo edit persistence','exact-size portrait/joint PDFs','library restart with lazy images','source preservation','2x2 and custom grid PDFs','maximum-fit landscape layout','live quantities preserve placements','profile application preserves layers','crop undo and redo','removed serial recovery','fine-edge offline model inference','categorized settings','verified backup and cross-path restore','preferences survive restart'])
    except Exception as e:
        import traceback
        result=dict(passed=False,error=str(e),traceback=traceback.format_exc())
    finally:
        for window in windows:window.dirty=False;window.close()
        app.processEvents();QMessageBox.warning=old_warning;QMessageBox.question=old_question
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return 0 if result['passed'] else 1
