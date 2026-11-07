"""Opt-in isolated UX acceptance; device calls are simulated, never submitted.

Screenshots are actual Qt widgets, including a real QPdfView of exported PDFs.
The test cannot access a device: its HardwareProcess seam rejects every action.
"""
import os,json,time,hashlib,traceback,copy
from pathlib import Path

def verify_ux(demo_dir,destination):
    if os.environ.get('PRINTORA_UX_VERIFY')!='1' or not os.environ.get('LOCALAPPDATA'):raise ValueError('Use PRINTORA_UX_VERIFY=1 and fresh isolated LOCALAPPDATA')
    root=Path(os.environ['LOCALAPPDATA'])/'StudioPhotoMaker'
    if root.exists() and any(root.iterdir()):raise ValueError('UX verification refuses existing data')
    from PIL import Image,ImageDraw
    from PySide6.QtWidgets import QApplication,QMessageBox,QScrollArea
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtTest import QTest
    from app.ui.studio_window import StudioWindow
    from app.ui.hardware_process import HardwareProcess
    from app.ui.hardware import PrintDialog
    from app.services.imaging import load_image,prepare_layer,render_photo
    from app.services.cropping import detect_photo_regions,extract_region
    from app.services.pdf import export_pdf
    from app.services.layout import auto_layout,validate_layout
    from app.services.print_sessions import add_composition
    from app.models.domain import Job
    app=QApplication.instance() or QApplication([]);out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();checks=[];errors=[];screenshots=[];w=None;calls=[]
    original_start=HardwareProcess.start;original_question=QMessageBox.question;original_warning=QMessageBox.warning
    HardwareProcess.start=lambda self,kind,request,*args:calls.append((kind,request.get('action')))
    QMessageBox.question=lambda *args:QMessageBox.Discard
    QMessageBox.warning=lambda *args:errors.append(str(args[-1]))
    def check(name,value=True):
        if not value:raise AssertionError(name)
        checks.append(name)
    def wait():
        limit=time.monotonic()+120
        while w.busy or w.timer.isActive():
            app.processEvents();time.sleep(.005)
            if time.monotonic()>limit:raise RuntimeError('Worker timeout')
        app.processEvents()
        if errors:raise RuntimeError('; '.join(errors))
    def shot(name,widget=None):
        app.processEvents();QTest.qWait(120);path=out/(name+'.png');(widget or w).grab().save(str(path));screenshots.append(path.name)
    try:
        w=StudioWindow();w.show();wait();check('Thirteen labeled navigation routes',w.shell.navigation.count()==13 and all(w.shell.navigation.item(i).text() for i in range(13)))
        if os.environ.get('STUDIO_VERIFY_MODEL_DIR'):w.db.set('model_dir',os.environ['STUDIO_VERIFY_MODEL_DIR'])
        demo=Path(demo_dir);portrait_path=demo/'Pictures/IMG_0007.jpg'
        joint_path=next(iter(sorted(demo.glob('joint*.jpg'))),None)
        hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (portrait_path,joint_path) if p}
        if not portrait_path.is_file() or joint_path is None:raise ValueError('Supply the private demo directory for visual acceptance')
        image=load_image(portrait_path);regions=detect_photo_regions(image)
        w.hardware.scan_dialog.preview_canvas.display(image,regions[:1]);w.hardware.scan_dialog.message.setText('QA file preview from supplied demo — no scanner acquisition performed.')
        items=[w.tray.add(f'QA portrait {i+1}',extract_region(image,region),str(portrait_path)) for i,region in enumerate(regions[:4])]
        joint=w.tray.add('QA combined joint',load_image(joint_path),str(joint_path),kind='Joint')
        check('Real demo crops saved with serials',len(items)==4 and all(p.serial for p in items))
        w.use_crops('portrait',[items[0]]);wait();p=copy.deepcopy(w.photo);w.save_job()
        check('Local model removes background',bool(p.layers[0].mask) and prepare_layer(p.layers[0]).getchannel('A').getextrema()[0]==0)
        c=w.canvas;c.set_tool('rectangle');item=c.layers[c.active]
        def source_point(x,y):return c.mapFromScene(item.mapToScene(QPointF((x-.5)*item.pixmap().width(),(y-.5)*item.pixmap().height())))
        QTest.mousePress(c.viewport(),Qt.LeftButton,Qt.NoModifier,source_point(.45,.45));QTest.mouseMove(c.viewport(),source_point(.55,.55));QTest.mouseRelease(c.viewport(),Qt.LeftButton,Qt.NoModifier,source_point(.55,.55))
        from app.services.selections import selection_mask
        mapped=bool(c.selection) and selection_mask(c.selection,(100,100)).getpixel((50,50))==255
        QTest.keyClick(c,Qt.Key_Delete);wait();native_edit=bool(w.photo.layers[0].mask_strokes);w.undo_edit();wait()
        c.set_tool('ellipse');c.set_selection({'kind':'ellipse','points':[[.1,.08],[.9,.9]]});c.modify_selection('invert');c.edit_selection();wait()
        check('Selection creates nondestructive saved edit',mapped and native_edit and w.photo.layers[0].mask_strokes[-1]['kind']=='selection')
        w.undo_edit();wait();check('Selection mask undo',not w.photo.layers[0].mask_strokes);w.redo_edit();wait();w.undo_edit();wait();w.save_job()
        w.use_crops('joint',items[:2]);wait();joint_photo=copy.deepcopy(w.photo);w.save_job()
        check('Separate joint subjects keep editor dimensions',(joint_photo.width,joint_photo.height)==(55,45) and len(joint_photo.layers)==2)
        w.use_crops('joint',[joint]);wait();combined=copy.deepcopy(w.photo);w.save_job();check('Combined joint remains one layer',len(combined.layers)==1)
        multi=w.studio.multi;multi.job=multi.empty_job();multi.auto_orientation.setChecked(False)
        for photo in (p,joint_photo,combined):add_composition(multi.job,photo)
        multi.changed();wait();validate_layout(multi.job)
        check('Portrait and rotated joints share 45 × 55 mm footprint',all((r.width,r.height)==(45,55) for r in multi.job.placements))
        check('Only joints rotate on the sheet',all(r.rotation==(0 if r.photo_id==multi.job.photos[0].id else 90) for r in multi.job.placements))
        saved=multi.store.load(multi.session_id);validate_layout(saved);check('Session restores rotations',saved.to_dict()==multi.job.to_dict())
        export_pdf(saved,out/'mixed-upright.pdf');check('Rotated PDF exists',(out/'mixed-upright.pdf').stat().st_size>1000)
        # Source-coordinate selections survive ordinary preview refresh; UI only, no photo changes.
        pages=[('dashboard',lambda:w.home()),('scan',lambda:w.shell.open(w.hardware.scan_dialog)),
          ('cropper',lambda:w.open_cropper()),('portrait',lambda:(w.adopt_job(Job(photos=[copy.deepcopy(p)])),w.sync_controls(),w.stack.setCurrentIndex(1))),
          ('joint',lambda:(w.adopt_job(Job(photos=[copy.deepcopy(joint_photo)])),w.sync_controls(),w.stack.setCurrentIndex(1))),
          ('multi',lambda:w.studio.show(multi)),('library',lambda:w.studio.show(w.studio.library)),
          ('customers',lambda:w.studio.show(w.studio.customer_page)),('orders',lambda:w.studio.show(w.studio.order_page)),
          ('recipes',w.shell.open_recipes),('tools',lambda:w.studio.show(w.studio.tools)),('settings',w.shell.open_settings),
          ('copy',lambda:w.shell.open(w.shell.copy)),('nid',lambda:w.shell.open(w.shell.nid))]
        # Real synthetic documents are labeled to avoid confusing them with valid identity cards.
        fixtures=out/'fictional-inputs';fixtures.mkdir(exist_ok=True);card_paths=[]
        for side,color in [('Front','#b6d9cf'),('Back','#d7cdb3')]:
            path=fixtures/(side+'.png');im=Image.new('RGB',(1200,800),'white');draw=ImageDraw.Draw(im);draw.rectangle((70,80,1130,720),fill=color,outline='black',width=5);draw.text((150,250),'FICTIONAL TEST CARD - NOT VALID ID',fill='black');im.save(path,dpi=(300,300));card_paths.append(str(path))
        for page in (w.shell.copy,w.shell.nid):page.import_files(paths=card_paths);wait();page.dirty=False
        for theme in ('Dark','Light'):
            w.shell.set_theme(theme)
            for name,open_page in pages:
                w.dirty=False;open_page();wait()
                if name in ('portrait','joint'):
                    w.editor_tabs.setCurrentIndex(w.editor_tabs.count()-1);w.canvas.set_selection({'kind':'ellipse','points':[[.2,.1],[.8,.8]]});w.canvas.set_tool('ellipse')
                shot(theme.lower()+'-'+name)
            check(theme+' native workspace screenshots',True)
        w.dirty=False;w.home();wait()
        for width,height in ((1050,740),(1366,768),(1920,1080)):
            w.setFixedSize(width,height);app.processEvents();shot(f'dashboard-render-{width}x{height}');check(f'Native widget render {width} × {height}',w.size().width()==width)
        available=app.primaryScreen().availableGeometry();w.setMinimumSize(0,0);w.setMaximumSize(16777215,16777215);w.shell.resize(min(1366,available.width()-20));app.processEvents();w.resize(min(1366,available.width()-20),min(768,available.height()-50));app.processEvents()
        check('Window fits current scaled logical screen',w.size().width()<=available.width() and w.size().height()<=available.height())
        folder=root/'print-spool'/'ux-review';folder.mkdir(parents=True);export_pdf(saved,folder/'sheet.pdf')
        h=w.hardware;h.printers=[dict(id='SIMULATED — NO OUTPUT',name='Simulated driver (QA only)',status='Ready',default=True)];h.populate(h.printer,h.printers,'SIMULATED — NO OUTPUT','None')
        d=PrintDialog(h,saved,folder);h.print_dialog=d;d.show();d.result({'area':dict(left=3,top=3,right=207,bottom=294)})
        check('Consolidated preview preflight',d.submit.isEnabled() and d.document.pageCount()==saved.page_count)
        for theme in ('Dark','Light'):w.shell.set_theme(theme);shot(theme.lower()+'-print-setup',d)
        check('No physical acquisition or print action',not any(action in ('scan','print') for _,action in calls))
        check('Original demo bytes unchanged',all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in hashes.items()))
        check('SQLite integrity',all(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not db.execute('PRAGMA foreign_key_check').fetchall() for db in (w.db.conn,w.tray.conn)))
        check('No unexpected dialogs',not errors)
        result=dict(passed=True,checks=checks,screenshots=screenshots,scale=os.environ.get('QT_SCALE_FACTOR','1'),physical_scan=False,physical_print=False,screen=[available.width(),available.height()])
    except Exception as error:result=dict(passed=False,checks=checks,screenshots=screenshots,error=repr(error),traceback=traceback.format_exc(),errors=errors)
    finally:
        if w:
            w.timer.stop();w.pool.waitForDone();app.processEvents();w.invalidate_autosave();w.dirty=False;w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.hardware.printing=False;w.hardware.shutdown();w.close();app.processEvents()
        HardwareProcess.start=original_start;QMessageBox.question=original_question;QMessageBox.warning=original_warning
    result['seconds']=round(time.monotonic()-started,2);(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
