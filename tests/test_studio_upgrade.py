import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import zipfile

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image,ImageDraw
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QPointF
from app.core.database import Database,starter_profiles
from app.models.domain import Job,Photo,Layer
from app.services.cropping import CropTray,detect_photo_regions
from app.services.layout import auto_layout,layout_capacity,validate_layout,resize_copies,mm_to_pt
from app.services.profiles import normalize_profile,apply_profile,REGIONS
from app.services.pdf import export_pdf
from app.services.imaging import render_photo,render_bordered_photo,export_photo_image,refine_alpha,reduce_halo
from app.services.storage import backup_data,prepare_restore,install_restore,clear_safe_cache,recover_restore
from app.ui.studio_window import StudioWindow
from app.ui.studio_settings import StudioSettings
from app.ui.canvas import PrintCanvas,PrintItem


def make_layout(photo,**settings):
    job=Job(photos=[photo]);job.print_settings.update(margin=10,gap_x=.2,gap_y=.2,enforce_margins=True,**settings)
    job.placements=auto_layout(job.photos,job.print_settings);job.page_count=max(p.page for p in job.placements)+1;validate_layout(job);return job


@pytest.mark.parametrize('width,height,kind',[(45,55,'Individual'),(55,45,'Combined joint')])
@pytest.mark.parametrize('landscape',[False,True])
def test_two_by_two_centered_exact_sizes_and_pagination(width,height,kind,landscape,tmp_path):
    source=tmp_path/'photo.png';Image.new('RGB',(500,400),'orange').save(source)
    job=make_layout(Photo(width=width,height=height,kind=kind,quantity=9,layers=[Layer(str(source))]),layout='grid_2x2',landscape=landscape)
    assert job.page_count==3
    first=[p for p in job.placements if p.page==0]
    assert len(first)==4 and len({r.x for r in first})==2 and len({r.y for r in first})==2
    pw,ph=(297,210) if landscape else (210,297)
    assert min(r.x for r in first)==pytest.approx(pw-max(r.x+r.width for r in first))
    assert min(r.y for r in first)==pytest.approx(ph-max(r.y+r.height for r in first))
    target=tmp_path/'two-by-two.pdf';export_pdf(job,target);reader=PdfReader(target);assert len(reader.pages)==3
    for page in reader.pages:
        assert float(page.mediabox.width)==pytest.approx(mm_to_pt(pw),abs=.0001)
        assert float(page.mediabox.height)==pytest.approx(mm_to_pt(ph),abs=.0001)
    assert all((r.width,r.height)==(width,height) for r in job.placements)


def test_custom_grid_max_fit_and_fit_explanation():
    job=make_layout(Photo(width=35,height=45,quantity=17),layout='custom',columns=3,rows=2)
    assert job.page_count==3 and len([r for r in job.placements if r.page==0])==6
    assert layout_capacity(Photo(),dict(layout='max_fit',margin=10,gap_x=.2,gap_y=.2))==(4,5)
    with pytest.raises(ValueError,match='will not fit without resizing'):
        make_layout(Photo(),layout='custom',columns=5,rows=2)
    with pytest.raises(ValueError,match='margins'):
        make_layout(Photo(width=200,height=290),layout='max_fit')
    job.placements[0].x=0
    with pytest.raises(ValueError,match='margins'):validate_layout(job)


def test_large_copy_orders_keep_identity_without_overlaps():
    job=make_layout(Photo(quantity=4),layout='max_fit');job.photos[0].quantity=10000
    resize_copies(job);validate_layout(job)
    assert len(job.placements)==10000 and len({r.copy for r in job.placements})==10000


def test_excessive_raster_export_fails_before_allocating_an_image():
    with pytest.raises(ValueError,match='50 megapixels'):render_photo(Photo(width=1000,height=1000),600)


def test_sheet_preview_vector_border_matches_exact_pdf_footprint(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'photo.png';Image.new('RGB',(40,60),'orange').save(source)
    photo=Photo(border_mm=.2,border_color='#334455',layers=[Layer(str(source))]);job=make_layout(photo,layout='grid_2x2')
    canvas=PrintCanvas();canvas.display(job,0,{photo.id:render_photo(photo,120)},vector_borders=True)
    items=[item for item in canvas.scene().items() if isinstance(item,PrintItem)];assert len(items)==4
    for item in items:
        bounds=item.border_item.sceneBoundingRect();assert bounds.width()==pytest.approx(photo.width*3) and bounds.height()==pytest.approx(photo.height*3)
        assert bounds.x()==pytest.approx(item.r.x*3) and bounds.y()==pytest.approx(item.r.y*3)
        assert item.border_item.pen().widthF()/3==pytest.approx(photo.border_mm)
        assert item.border_item.pen().color().name()=='#334455'
    canvas.close()


def test_low_contrast_print_detection_preserves_source():
    image=Image.new('RGB',(400,400),(250,250,250));draw=ImageDraw.Draw(image)
    draw.rectangle((30,30,140,195),fill=(235,235,235));draw.rectangle((245,180,360,350),fill=(235,235,235));before=image.tobytes()
    assert len(detect_photo_regions(image))==2 and image.tobytes()==before


def test_quantity_changes_keep_manual_copy_positions():
    job=make_layout(Photo(quantity=4),layout='grid_2x2');job.placements[0].x-=1
    before={(r.photo_id,r.copy):(r.x,r.y,r.page) for r in job.placements}
    job.photos[0].quantity=10;resize_copies(job);validate_layout(job)
    assert job.page_count==3 and len(job.placements)==10
    assert all((r.x,r.y,r.page)==before[(r.photo_id,r.copy)] for r in job.placements if r.copy<4)
    job.photos[0].quantity=2;resize_copies(job);validate_layout(job)
    assert len(job.placements)==2 and job.page_count==1


def test_profiles_additive_migration_and_layer_preservation(tmp_path):
    path=tmp_path/'old.db';db=Database(path);job=make_layout(Photo(),layout='grid_2x2');db.save_job(job)
    old=dict(name='Customer preset',width=45,height=55,background='#abcdef',border_color='#123456')
    with db.conn:
        db.conn.execute('DELETE FROM profiles')
        db.conn.execute('INSERT INTO profiles VALUES(?,?)',(old['name'],json.dumps(old)))
        db.conn.execute('DELETE FROM config WHERE key=?',('profile_schema_version',))
    payload=db.conn.execute('SELECT payload FROM jobs WHERE id=?',(job.id,)).fetchone()[0];db.conn.close()
    db=Database(path);assert next(p for p in db.profiles() if p['name']=='Customer preset')==old
    assert db.conn.execute('SELECT payload FROM jobs WHERE id=?',(job.id,)).fetchone()[0]==payload
    assert set(REGIONS).issubset({normalize_profile(p)['country'] for p in db.profiles()})
    profile=normalize_profile(dict(old,quantity=8,border_mm=.35,layout='grid_2x2'))
    photo=Photo(layers=[Layer('source.png',x=.31,rotation=12,mask_strokes=[dict(mode='erase',points=[[.1,.2]],radius=.03)])]);layers=copy.deepcopy(photo.layers)
    apply_profile(photo,profile,job.print_settings);assert photo.layers==layers and photo.quantity==8 and photo.border_color=='#123456'
    db.save_profile(profile);db.set('default_profile',profile['name']);db.rename_profile(profile['name'],dict(profile,name='Renamed custom'))
    assert db.get('default_profile')=='Renamed custom';db.conn.close()
    db=Database(path);assert any(p['name']=='Renamed custom' for p in db.profiles());db.conn.close()


def test_legacy_library_migration_and_deleted_recovery(tmp_path):
    root=tmp_path/'library';root.mkdir();conn=sqlite3.connect(root/'library.db')
    conn.execute('CREATE TABLE photos(serial INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,name TEXT,source TEXT,asset TEXT,thumb TEXT,width INTEGER,height INTEGER,deleted INTEGER DEFAULT 0)')
    image=root/'old.png';Image.new('RGB',(90,60),'blue').save(image)
    conn.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,?,?,?)',(41,'old','Old combined','',''+str(image),'',90,60,0));conn.commit();conn.close()
    tray=CropTray(root=root);assert tray.items[0].serial==41 and tray.items[0].kind=='Joint'
    tray.remove({'old'});assert not tray.items;assert tray.query(deleted=True)[0].serial==41
    tray.restore_items({'old'});assert tray.items[0].serial==41 and image.exists()
    new=tray.add('New portrait',Image.new('RGB',(30,40),'red'));assert new.serial==42
    tray.set_kind({new.id},'Joint');assert tray.query(kind='Joint',sort='oldest')[0].serial==41;tray.close()
    tray=CropTray(root=root);assert tray.items[-1].kind=='Joint';tray.close()


def test_reimport_missing_source_retains_source_serial(tmp_path):
    original=tmp_path/'source.png';Image.new('RGB',(30,40),'red').save(original)
    tray=CropTray(root=tmp_path/'library');saved=tray.import_source(original);serial=tray.sources()[0][0];Path(saved).unlink()
    tray.import_source(original);assert tray.sources()[0][0]==serial;tray.close()


def test_migrate_copy_of_previous_release_data_without_changing_original(tmp_path):
    previous=Path(__file__).resolve().parents[1]/'.tools'/'studio-release-data'/'StudioPhotoMaker'
    if not (previous/'studio.db').exists():pytest.skip('Previous local release acceptance data is absent.')
    originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (previous/'studio.db',previous/'library'/'library.db')}
    def snapshot(source,target):
        target.parent.mkdir(parents=True,exist_ok=True);src=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(target)
        try:src.backup(dst)
        finally:src.close();dst.close()
    snapshot(previous/'studio.db',tmp_path/'studio.db');snapshot(previous/'library'/'library.db',tmp_path/'library'/'library.db')
    conn=sqlite3.connect(tmp_path/'studio.db');jobs=conn.execute('SELECT id,payload FROM jobs ORDER BY id').fetchall();conn.close()
    conn=sqlite3.connect(tmp_path/'library'/'library.db');photos=conn.execute('SELECT serial,id,asset FROM photos ORDER BY serial').fetchall();conn.close()
    db=Database(tmp_path/'studio.db');assert db.conn.execute('SELECT id,payload FROM jobs ORDER BY id').fetchall()==jobs;db.conn.close()
    tray=CropTray(root=tmp_path/'library');assert tray.conn.execute('SELECT serial,id,asset FROM photos ORDER BY serial').fetchall()==photos;tray.close()
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in originals.items())


def studio_data(root,external):
    root.mkdir();db=Database(root/'studio.db');tray=CropTray(root=root/'library')
    item=tray.add('Numbered photo',Image.new('RGB',(90,110),'orange'))
    mask=root/'cache'/'used.png';mask.parent.mkdir();Image.new('RGBA',(90,110),'orange').save(mask)
    photo=Photo(layers=[Layer(item.asset,str(mask)),Layer(str(external),x=.7,scale=.3)])
    job=make_layout(photo,layout='grid_2x2');db.save_job(job);db.set('output',str(root/'exports'));db.conn.close();tray.close();return job,item


def test_verified_backup_restore_remaps_paths_keeps_serials_and_previous_data(tmp_path):
    external=tmp_path/'external.png';Image.new('RGB',(40,60),'green').save(external)
    root=tmp_path/'old-app';job,item=studio_data(root,external);original=external.read_bytes();archive=tmp_path/'backup.zip'
    backup_data(root,archive);target=tmp_path/'restored-app';target.mkdir();(target/'keep.txt').write_text('previous data')
    stage=prepare_restore(archive,target);assert (target/'keep.txt').exists()
    previous=Path(install_restore(stage,target));assert (previous/'keep.txt').read_text()=='previous data'
    db=Database(target/'studio.db');loaded=db.load_job(job.id);assert loaded.placements==job.placements
    for layer in loaded.photos[0].layers:
        assert Path(layer.source).is_relative_to(target) and Path(layer.source).exists()
        if layer.mask:assert Path(layer.mask).exists()
    assert render_photo(loaded.photos[0]).tobytes()==render_photo(job.photos[0]).tobytes()
    assert db.get('output')==str(target/'exports');db.conn.close()
    tray=CropTray(root=target/'library');assert tray.items[0].serial==item.serial
    assert tray.add('Next',Image.new('RGB',(20,30),'blue')).serial==item.serial+1;tray.close();assert external.read_bytes()==original


def test_backup_corruption_and_path_traversal_leave_current_data_untouched(tmp_path):
    external=tmp_path/'external.png';Image.new('RGB',(20,30),'green').save(external)
    root=tmp_path/'data';studio_data(root,external);valid=tmp_path/'valid.zip';backup_data(root,valid)
    broken=tmp_path/'broken.zip'
    with zipfile.ZipFile(valid) as source,zipfile.ZipFile(broken,'w') as output:
        for name in source.namelist():output.writestr(name,b'broken' if name=='studio.db' else source.read(name))
    with pytest.raises(ValueError,match='integrity'):prepare_restore(broken,root)
    assert (root/'studio.db').exists()
    malicious=tmp_path/'malicious.zip'
    with zipfile.ZipFile(malicious,'w') as output:
        output.writestr('backup-manifest.json',json.dumps(dict(format=1,source_root='old',files={'../escape':{},'studio.db':{}})))
        output.writestr('../escape','bad');output.writestr('studio.db','bad')
    with pytest.raises(ValueError,match='Unsafe'):prepare_restore(malicious,root)
    assert not (tmp_path/'escape').exists()


def test_cache_cleanup_protects_all_saved_and_open_job_assets(tmp_path):
    external=tmp_path/'external.png';Image.new('RGB',(20,30),'green').save(external)
    root=tmp_path/'data';job,_=studio_data(root,external);cache=root/'cache';orphan=cache/'unused.png';live=cache/'open-edit.png'
    for path in (orphan,live):Image.new('RGBA',(20,30),'red').save(path)
    for path in cache.iterdir():os.utime(path,(time.time()-200000,)*2)
    result=clear_safe_cache(root,[live]);assert result['files']==1 and not orphan.exists()
    assert live.exists() and Path(job.photos[0].layers[0].mask).exists() and external.exists()


def test_borders_image_export_and_guided_matte_preserve_original(tmp_path):
    source=tmp_path/'original.png';im=Image.new('RGBA',(100,150),(220,220,220,0));ImageDraw.Draw(im).rectangle((20,20,80,149),fill=(100,70,50,255));im.save(source);original=source.read_bytes()
    photo=Photo(width=45,height=55,border_color='#bc2167',border_mm=.45,layers=[Layer(str(source),defringe=.5)])
    preview=render_bordered_photo(photo);assert preview.getpixel((0,0))==(188,33,103)
    target=tmp_path/'edited.png';export_photo_image(photo,target);assert Image.open(target).tobytes()==preview.tobytes()
    job=make_layout(photo,layout='grid_2x2');pdf=tmp_path/'border.pdf';export_pdf(job,pdf);page=PdfReader(pdf).pages[0]
    assert page.images[0].image.convert('RGB').tobytes()==render_photo(photo).tobytes()
    rectangles=[args for args,operator in page.get_contents().operations if operator==b're']
    assert float(rectangles[0][2])==pytest.approx(mm_to_pt(45-.45),abs=.0001)
    strokes=[args for args,operator in page.get_contents().operations if operator==b'RG']
    assert tuple(float(v) for v in strokes[0])==pytest.approx((188/255,33/255,103/255),abs=.00001)
    alpha=im.getchannel('A');refined=refine_alpha(im,alpha);assert refined.size==im.size and refined.getpixel((50,100))==255
    assert reduce_halo(im,.8).getchannel('A').tobytes()==alpha.tobytes();assert source.read_bytes()==original


def test_interrupted_restore_recovers_before_creating_an_empty_data_folder(tmp_path,monkeypatch):
    external=tmp_path/'external.png';Image.new('RGB',(20,30),'green').save(external)
    root=tmp_path/'old';studio_data(root,external);backup=tmp_path/'backup.zip';backup_data(root,backup)
    destination=tmp_path/'StudioPhotoMaker';destination.mkdir();(destination/'old-state.txt').write_text('retained')
    stage=Path(prepare_restore(backup,destination));previous=tmp_path/'StudioPhotoMaker.before-restore-simulated'
    destination.rename(previous)
    journal=tmp_path/'StudioPhotoMaker.restore-pending.json';journal.write_text(json.dumps(dict(destination=str(destination),stage=str(stage),previous=str(previous))))
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    from app.core.database import data_root
    assert data_root()==destination and (destination/'studio.db').exists()
    assert (previous/'old-state.txt').exists() and not journal.exists()


def test_invalid_preferences_do_not_write_partial_changes(tmp_path):
    app=QApplication.instance() or QApplication([]);db=Database(tmp_path/'studio.db')
    settings=StudioSettings(db,lambda *args:None,lambda *args:None,lambda:None)
    settings.fields['quantity'].setValue(7);settings.fields['background'].setText('not a color');settings.save()
    assert db.get('quantity',4)==4 and 'not saved' in settings.message.text();settings.close();db.conn.close()


def test_default_profile_selection_updates_new_job_dimensions(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);window=StudioWindow()
    settings=StudioSettings(window.db,window.run,window.notify,lambda:None)
    combo=settings.fields['default_profile'];combo.setCurrentIndex(combo.findData('USA Passport'));settings.save()
    window.start_workflow('portrait');assert (window.photo.width,window.photo.height)==(51,51) and window.photo.background=='#FFFFFF'
    settings.close();window.dirty=False;window.close();app.processEvents()


def wait(app,window):
    deadline=time.monotonic()+40
    while (window.busy or window.timer.isActive()) and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert not window.busy and not window.timer.isActive()


def test_active_ui_live_quantities_profiles_crop_history_and_preferences(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));app=QApplication.instance() or QApplication([]);window=StudioWindow();window.show();errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda p,t,m:errors.append(m));monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Discard)
    source=tmp_path/'portrait.png';Image.new('RGB',(400,600),'orange').save(source)
    window.start_workflow('portrait');window.import_photos(paths=[str(source)]);wait(app,window)
    from PySide6.QtWidgets import QPushButton
    next(button for button in window.findChildren(QPushButton) if button.text()=='2').click();wait(app,window);assert window.photo.quantity==2
    window.quantity.setValue(4);wait(app,window)
    window.print_options.layout.setCurrentIndex(window.print_options.layout.findData('grid_2x2'));wait(app,window);window.show_print();wait(app,window)
    assert len(window.job.placements)==4;coordinates=[(r.x,r.y) for r in window.job.placements]
    window.change_quantity(2);wait(app,window);assert window.photo.quantity==6 and window.pages.count()==2 and window.sheet_quantity.value()==6
    assert [(r.x,r.y) for r in window.job.placements if r.copy<4]==coordinates
    window.change_quantity(-2);wait(app,window);assert len(window.job.placements)==4
    window.stack.setCurrentIndex(1);before=copy.deepcopy(window.photo.layers);window.profile_picker.setCurrentText('Studio Standard Photo');window.apply_selected_profile();wait(app,window)
    assert window.photo.layers==before and window.photo.width==35
    pixels=render_bordered_photo(window.photo).tobytes();window.guide.setChecked(False);window.guide.setChecked(True);assert render_bordered_photo(window.photo).tobytes()==pixels
    settings=StudioSettings(window.db,window.run,window.notify,lambda:None);settings.fields['quantity'].setValue(6);settings.fields['portrait_width'].setValue(40);settings.fields['portrait_height'].setValue(50);settings.print_options.gap_x.setValue(.4);settings.save()
    window.dirty=False;window.start_workflow('portrait');assert (window.photo.width,window.photo.height,window.photo.quantity)==(40,50,6)
    window.import_to_cropper(paths=[str(source)]);wait(app,window);cropper=window.cropper;count=len(cropper.regions);cropper.full_image();assert len(cropper.regions)==count+1
    cropper.undo_crop();assert len(cropper.regions)==count;cropper.redo_crop();assert len(cropper.regions)==count+1
    outline=cropper.canvas.outlines[0];old=copy.deepcopy(cropper.regions[0].points);handle=outline.handles[4];handle.setPos(handle.pos()+QPointF(0,10));outline.commit();cropper.undo_crop();assert cropper.regions[0].points==old
    window.dirty=False;settings.close();window.close();app.processEvents();window=StudioWindow();window.start_workflow('portrait');assert window.photo.quantity==6 and window.job.print_settings['gap_x']==.4
    window.dirty=False;window.close();app.processEvents();assert not errors
