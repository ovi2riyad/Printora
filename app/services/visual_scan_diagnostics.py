"""Opt-in visual and pointer acceptance with an inert scanner process seam."""
import copy
import hashlib
import json
import os
import time
import traceback
from pathlib import Path

def verify_visual_scan(demo,destination):
    if os.environ.get('PRINTORA_VISUAL_VERIFY')!='1' or not os.environ.get('LOCALAPPDATA'):raise ValueError('Use PRINTORA_VISUAL_VERIFY=1 and fresh isolated LOCALAPPDATA')
    root=Path(os.environ['LOCALAPPDATA'])/'StudioPhotoMaker'
    if root.exists() and any(root.iterdir()):raise ValueError('Visual verification refuses existing data')
    from PIL import Image,ImageDraw
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox
    from PySide6.QtTest import QTest
    from app.ui.studio_window import StudioWindow
    from app.ui.hardware_process import HardwareProcess
    from app.services.imaging import load_image,prepare_layer
    from app.services.cropping import detect_photo_regions,extract_region
    from app.services.selections import selection_mask
    from app.models.domain import Layer
    app=QApplication.instance() or QApplication([]);out=Path(destination);out.mkdir(parents=True,exist_ok=True);checks=[];screens=[];calls=[];w=None;errors=[];started=time.monotonic()
    old_start=HardwareProcess.start;old_text=QInputDialog.getText;old_question=QMessageBox.question;old_warning=QMessageBox.warning
    HardwareProcess.start=lambda self,*args:calls.append(args)
    QInputDialog.getText=lambda *a,**k:('Passport sheet',True)
    QMessageBox.question=lambda *a,**k:QMessageBox.Discard
    QMessageBox.warning=lambda *a,**k:errors.append(str(a[-1]))
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append(name)
    def settle():
        end=time.monotonic()+90
        while w.busy or w.timer.isActive():
            app.processEvents();time.sleep(.01)
            if time.monotonic()>end:raise TimeoutError('GUI worker')
        for _ in range(8):app.processEvents()
        if errors:raise RuntimeError('; '.join(errors))
    def shot(name):
        settle();QTest.qWait(100);path=out/(name+'.png');w.grab().save(str(path));screens.append(path.name)
    def drag(c,a,b,mod=Qt.NoModifier):
        QTest.mousePress(c.viewport(),Qt.LeftButton,mod,a);QTest.mouseMove(c.viewport(),b,30);QTest.mouseRelease(c.viewport(),Qt.LeftButton,mod,b);app.processEvents()
    try:
        w=StudioWindow();w.show();settle();w.setFixedSize(1366,768);app.processEvents()
        check('New installation opens in reference navy theme',w.property('themeMode')=='Dark' and not w.shell.hero.art.isNull())
        source=Path(demo)/'Pictures/IMG_0007.jpg';before=hashlib.sha256(source.read_bytes()).hexdigest();image=load_image(source);regions=detect_photo_regions(image)
        photos=[w.tray.add('QA supplied photo '+str(i+1),extract_region(image,r),str(source)) for i,r in enumerate(regions[:4])]
        w.shell.refresh_overview();shot('dashboard-dark')
        check('Four colored workflow tiles share one row',len({card.y() for card in w.shell.action_cards})==1 and all(card.size().height()>=148 for card in w.shell.action_cards))
        p=photos[0].asset;w.start_workflow('portrait')
        check('New portrait defaults to the 42 x 52 mm recipe',(w.photo.width,w.photo.height)==(42,52) and w.photo.profile=='Studio Portrait 42 x 52 mm')
        supplied=Path(demo)/'IMG.jpg'
        if supplied.is_file():
            supplied_before=hashlib.sha256(supplied.read_bytes()).hexdigest();single=load_image(supplied);single_regions=detect_photo_regions(single)
            check('Supplied bordered portrait yields one complete print',len(single_regions)==1 and extract_region(single,single_regions[0]).height>=388)
            check('Supplied portrait original unchanged',hashlib.sha256(supplied.read_bytes()).hexdigest()==supplied_before)
        w.photo.layers=[Layer(str(p),label=photos[0].display_name)];w.sync_controls();w.timer.stop();w.render_preview();settle()
        c=w.canvas
        def point(x,y):
            item=c.layers[c.active];return c.mapFromScene(item.mapToScene(QPointF((x-.5)*item.pixmap().width(),(y-.5)*item.pixmap().height())))
        index=w.shape_picker.findData('ellipse');w.shape_picker.setCurrentIndex(index);w.shape_picker.activated.emit(index)
        drag(c,point(.35,.3),point(.5,.38),Qt.ShiftModifier)
        item=c.layers[c.active];a,b=c.selection['points'];check('Shift-drag creates a pixel-circular selection',abs(abs(b[0]-a[0])*item.pixmap().width()-abs(b[1]-a[1])*item.pixmap().height())<2)
        drag(c,point(.55,.55),point(.65,.62),Qt.ControlModifier|Qt.ShiftModifier);check('Ctrl+Shift adds another circle',c.selection['kind']=='add')
        QTest.keyClick(c,Qt.Key_Delete);settle();check('Delete commits a mask edit',len(w.photo.layers[0].mask_strokes)==1 and prepare_layer(w.photo.layers[0]).getchannel('A').getextrema()[0]==0)
        shot('portrait-delete');w.undo_edit();settle();check('Undo restores pixels',not w.photo.layers[0].mask_strokes);w.dirty=False
        h=w.hardware;d=h.scan_dialog;h.scanners=[dict(id='SIMULATED',name='QA simulated scanner — no physical scan',status='Simulated',backend='wia')];h.populate(h.scanner,h.scanners,'SIMULATED','None');d.update_devices()
        caps=dict(id='flatbed',name='Flatbed',width_mm=230,height_mm=330,resolutions=[100,300,600],colors=['color','gray'])
        d.result('capabilities',dict(sources=[caps],status='Simulated capabilities'));w.shell.open(d);settle();d.set_region([10,20,50,60]);d.scan_now(preview=True)
        check('Preview requests the full bed at low DPI',calls[-1][1]['region']==[0,0,230,330] and calls[-1][1]['dpi']==100)
        # Feed a file preview into the GUI seam; no device process is started.
        frame=Image.new('RGB',(690,990),'#d6d9df');draw=ImageDraw.Draw(frame);draw.text((18,16),'QA FILE PREVIEW - NO SCANNER ACQUISITION',fill='black')
        for i,photo in enumerate(photos):
            crop=photo.image.copy();crop.thumbnail((180,225));frame.paste(crop,(90+i%2*220,110+i//2*300))
        d.set_scanning(False);d.display_preview(frame);v=d.preview_canvas
        drag(v,v.mapFromScene(QPointF(75,90)),v.mapFromScene(QPointF(510,690)))
        roi=[box.value() for box in d.region];check('Pointer drawing applies hardware ROI automatically',abs(roi[0]-25)<2 and abs(roi[2]-145)<2 and d.apply_area.isHidden())
        d.save_area();check('Named area persisted',w.db.get('scan_area_presets')['Passport sheet']['region']==roi)
        d.paper_changed(1);check('A4 shortcut', [box.value() for box in d.region]==[0,0,210,297])
        d.paper_changed(2);check('Letter shortcut',[box.value() for box in d.region]==[0,0,215.9,279.4])
        d.use_preset(d.area_presets.findData('Passport sheet'));check('Named area reused',[box.value() for box in d.region]==roi)
        d.scan_now();check('Final scan uses selected ROI and DPI',calls[-1][1]['region']==roi and calls[-1][1]['dpi']==300);d.set_scanning(False)
        d.verified(dict(width=120,height=160,format='PNG',original=str(p)))
        check('Cropped acquisition retains the full bed for repeat selections',d.preview_image is frame and d.preview_acquired_region==[0,0,230,330])
        drag(v,v.mapFromScene(QPointF(150,210)),v.mapFromScene(QPointF(360,480)))
        repeat=[box.value() for box in d.region]
        check('Dragging inside the old rectangle draws a replacement',abs(repeat[0]-50)<2 and abs(repeat[1]-70)<2 and abs(repeat[2]-70)<2 and abs(repeat[3]-90)<2)
        h.twain_devices(dict(devices=[]))
        check('Late device discovery retains preview and capabilities',d.preview_image is frame and d.sources==[caps] and [box.value() for box in d.region]==repeat)
        d.scan_now();check('Repeated selection uses its own exact ROI',calls[-1][1]['region']==repeat);d.set_scanning(False);shot('scan-selected-area')
        for theme in ('Light','Dark'):
            w.shell.set_theme(theme);w.home();shot('dashboard-'+theme.lower()+'-final')
            w.shell.open(d);shot('scan-'+theme.lower())
        for width,height in ((1050,740),(1920,1080)):
            w.setFixedSize(width,height);w.home();shot(f'dashboard-{width}x{height}')
        check('Source bytes unchanged',hashlib.sha256(source.read_bytes()).hexdigest()==before)
        check('Main and library SQLite integrity',all(conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not conn.execute('PRAGMA foreign_key_check').fetchall() for conn in (w.db.conn,w.tray.conn)))
        check('All device requests intercepted',all(args[1]['action'] in ('scan','capabilities') for args in calls))
        result=dict(passed=True,checks=checks,screenshots=screens,physical_scan=False,physical_print=False,scale=os.environ.get('QT_SCALE_FACTOR','1'))
    except Exception as error:result=dict(passed=False,checks=checks,error=repr(error),traceback=traceback.format_exc(),screenshots=screens)
    finally:
        if w:
            w.timer.stop();w.pool.waitForDone();app.processEvents();w.invalidate_autosave();w.dirty=False;w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.hardware.shutdown();w.close();app.processEvents()
        HardwareProcess.start=old_start;QInputDialog.getText=old_text;QMessageBox.question=old_question;QMessageBox.warning=old_warning
    result['seconds']=round(time.monotonic()-started,2);(out/'result.json').write_text(json.dumps(result,indent=2),'utf-8');print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
