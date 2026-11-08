"""Opt-in source/frozen UI acceptance. All scanner/printer processes are inert."""
import hashlib
import copy
import json
import os
import time
import traceback
from pathlib import Path


def verify_simple_workflows(destination):
    if os.environ.get('PRINTORA_SIMPLE_VERIFY')!='1' or not os.environ.get('LOCALAPPDATA'):
        raise ValueError('Use PRINTORA_SIMPLE_VERIFY=1 and fresh isolated LOCALAPPDATA')
    root=Path(os.environ['LOCALAPPDATA'])/'StudioPhotoMaker'
    if root.exists() and any(root.iterdir()):raise ValueError('Verification refuses existing application data')
    from PIL import Image,ImageDraw
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QMessageBox,QLabel
    from app.ui.studio_window import StudioWindow
    from app.ui.hardware_process import HardwareProcess
    from app.models.domain import Layer
    from app.version import VERSION
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);w=None;calls=[];checks=[];screens=[];errors=[];started=time.monotonic()
    old_start=HardwareProcess.start;old_question=QMessageBox.question;old_warning=QMessageBox.warning
    HardwareProcess.start=lambda self,*args:calls.append(args)
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
    def shot(name,widget=None):
        settle();QTest.qWait(100);(widget or w).grab().save(str(out/(name+'.png')));screens.append(name+'.png')
    def requests(action):return [args[1] for args in calls if args[1]['action']==action]
    def transfer(name,color):
        path=out/(name+'.png');Image.new('RGB',(1240,1754),color).save(path,dpi=(150,150))
        request=w.hardware.scan_request
        w.hardware.scan_dialog.completion_callback(dict(original=str(path),driver=dict(dpi=request['dpi'])))
        settle();return path
    def submit(color):
        dialog=w.hardware.print_dialog;before=len(requests('print'))
        check('One-click request opens an automatic direct print intent',dialog is not None and dialog.direct_requested and dialog.auto_requested)
        dialog.result(dict(area=dict(left=0,top=0,right=210,bottom=297)))
        check('Exactly one selected-printer submission without another click',len(requests('print'))==before+1 and requests('print')[-1]['automatic'] is False)
        check('Requested driver color is retained',requests('print')[-1]['color']==color)
        dialog.result(dict(status='Simulated submission only'));dialog.close();w.hardware.printing=False
    ok=False
    try:
        w=StudioWindow();w.showMaximized();settle();app.processEvents()
        h=w.hardware;d=h.scan_dialog
        h.scanners=[dict(id='QA-SCANNER',name='QA scanner — no hardware acquisition',status='Simulated',backend='wia')]
        h.printers=[dict(id='QA-PRINTER',name='QA printer — no hardware output',status='Queue available; physical readiness unverified',default=True)]
        h.populate(h.scanner,h.scanners,'QA-SCANNER','None');h.populate(h.printer,h.printers,'QA-PRINTER','None');d.update_devices()
        d.result('capabilities',dict(sources=[dict(id='bed',name='Flatbed',width_mm=230,height_mm=330,resolutions=[100,150,300,600],colors=['color','gray'])],status='Simulated'))
        c=w.shell.copy;n=w.shell.nid;c.update_printers();n.update_printers()
        w.shell.open(d);settle()
        check('Scan main exposes scanner and 300 DPI with A4 default',d.device.isVisible() and d.dpi.isVisible() and d.dpi.currentData()==300 and [v.value() for v in d.region]==[0,0,210,297])
        check('Advanced scan and under-preview controls live in Settings',not d.color.isVisible() and not d.area_presets.isVisible())
        shot('scan-main');d.advanced_settings.open_settings();shot('scan-settings',d.advanced_settings);d.advanced_settings.hide()
        d.scan_now(preview=True);check('Preview requests full bed at low DPI',requests('scan')[-1]['region']==[0,0,230,330] and requests('scan')[-1]['dpi']==100);d.set_scanning(False)
        w.shell.open(c);settle();shot('quick-copy-main')
        check('Copy main exposes only principal actions and device/quantity controls',c.color_copy.isVisible() and c.bw_copy.isVisible() and c.fields['copies'].isVisible() and not c.primary_print.isVisible())
        originals=[]
        for color in ('color','gray'):
            c.fields['copies'].setValue(2);c.start_copy(color)
            check('Copy requests its own 150 DPI A4 without changing Scan defaults',h.scan_request['dpi']==150 and h.scan_request['region']==[0,0,210,297] and h.scan_request['color']==color and w.db.get('scan_dpi',300)==300)
            originals.append(transfer('copy-'+color,'white'));submit(color)
            check('Copy count is encoded once in the print document',h.print_dialog.job.page_count==2)
        c.start_copy('color',True);originals.append(transfer('set-first','red'));count=len(requests('print'))
        check('Completed set page offers Add and Finish without printing',c.add_page_button.isEnabled() and c.finish_set_button.isEnabled() and len(requests('print'))==count)
        c.add_set_page();originals.append(transfer('set-second','blue'));c.finish_set();c.finish_set();settle()
        check('Two-page two-copy set is collated and Finish cannot duplicate it',h.print_dialog.job.page_count==4 and [p.copy for p in h.print_dialog.job.placements]==[0,0,1,1]);submit('color')
        c.dirty=False;w.shell.open(n)
        cards=[]
        for index,color in enumerate(('blue','orange')):
            path=out/('card-'+str(index)+'.png');im=Image.new('RGB',(1000,800),'white');ImageDraw.Draw(im).rectangle((100,150,900,650),fill=color,outline='black',width=5);im.save(path,dpi=(300,300));cards.append(path)
        hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals+cards}
        n.import_files(paths=[str(p) for p in cards]);settle();p=n.preview_dialog
        check('Two imports auto-detect and accept front/back then open actual PDF',p is not None and p.job is not None and len(n.reviewed)==2 and all(x.points for x in n.session.pages))
        check('Each PDF side has four square crop handles',len(p.handles)==2 and all(len(items)==4 for items in p.handles.values()))
        shot('nid-main');shot('nid-pdf',p)
        handle=p.handles[0][0];a=p.view.mapFromScene(handle.scenePos());b=a+QPoint(15,12);old=p.path
        QTest.mousePress(p.view.viewport(),Qt.LeftButton,Qt.NoModifier,a)
        check('Press reveals translucent original scan',p.overlay is not None and p.overlay.opacity()==.35)
        shot('nid-transparent-source',p);QTest.mouseMove(p.view.viewport(),b,30);QTest.mouseRelease(p.view.viewport(),Qt.LeftButton,Qt.NoModifier,b);settle()
        check('Corner drag regenerates cropped PDF',p.path!=old)
        p.print_pdf();settle();submit('color');p.close();n.dirty=False
        n.clear(confirm=False);combined=out/'combined.png';im=Image.new('RGB',(1200,1600),'white');draw=ImageDraw.Draw(im);draw.rectangle((100,100,1100,700),fill='blue',outline='black',width=5);draw.rectangle((150,900,1050,1450),fill='orange',outline='black',width=5);im.save(combined,dpi=(300,300));hashes[str(combined)]=hashlib.sha256(combined.read_bytes()).hexdigest()
        n.import_files(paths=[str(combined)]);settle()
        check('One combined file supplies two independent nondestructive sides',len(n.session.pages)==2 and n.session.pages[0].points!=n.session.pages[1].points and n.preview_dialog.job.page_count==1)
        n.preview_dialog.close();n.dirty=False
        supplied=os.environ.get('PRINTORA_NID_VERIFY_DEMO')
        if supplied:
            import cv2,shutil
            from app.services.cropping import order_quad
            paths=[Path(supplied)/name for name in ('front.jpg','back.jpg')]
            for path in paths:hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            n.clear(confirm=False);n.import_files(paths=[str(path) for path in paths]);settle()
            check('Supplied front and back scans both detect the complete outer card',all(len(page.points)==4 and cv2.contourArea(order_quad(page.points))>590_000 for page in n.session.pages))
            check('Supplied NID PDF contains two full-size card footprints on one page',n.preview_dialog.job.page_count==1 and all(80<photo.width<87 and 49<photo.height<55 for photo in n.preview_dialog.job.photos))
            shot('supplied-nid-pdf',n.preview_dialog);shutil.copyfile(n.preview_dialog.path,out/'supplied-nid.pdf')
            for index,page in enumerate(n.session.pages):
                processed,_=n.session.prepared(page,n.settings());shutil.copyfile(processed,out/('supplied-side-'+str(index)+'.png'))
            n.preview_dialog.close();n.dirty=False
        for kind in ('portrait','joint'):
            w.start_workflow(kind);w.photo.layers=[Layer(str(cards[0]))];w.sync_controls();w.quantity.setValue(6);w.timer.stop();w.render_preview();settle()
            check(kind+' has top preview, quantity and Settings',w.top_preview.isVisible() and w.quantity.isVisible() and w.photo_settings_button.isVisible() and w.photo.quantity==6 and not w.scale.isVisible())
            check(kind+' has a floating processing panel and no page scrolling',w.floating_tabs.currentIndex()==0 and w.denoise.isVisible() and w.editor_panel.parentWidget() is w.editor_splitter and w.shell.workspace_scroll.verticalScrollBar().maximum()==0)
            w.denoise.setValue(.2);w.shadows.setValue(.15);w.auto_soften.click();settle()
            check(kind+' softener is reversible and preserves the other processing settings',w.photo.layers[0].skin_soften>0)
            w.auto_soften.click();settle()
            check(kind+' retains noise/shadow processing after disabling softening',w.photo.layers[0].skin_soften==0 and w.photo.layers[0].denoise==.2 and w.photo.layers[0].shadows==.15)
            w.canvas.fit_preview();settle();bounds=w.canvas.mapFromScene(w.canvas.photo_rect).boundingRect()
            available_width=max(20,w.canvas.viewport().width()-w.canvas.preview_obstruction-20)
            expected_height=min(max(20,w.canvas.viewport().height()-20),available_width*w.canvas.photo_rect.height()/w.canvas.photo_rect.width())
            check(kind+' fits the actual photo tightly beside floating controls',bounds.height()>=expected_height-3 and bounds.right()<w.editor_panel.mapTo(w.canvas.viewport(),QPoint()).x()+8)
            snapshot=w.edit_snapshot();w.auto_fix.click();settle();first=copy.deepcopy(w.photo.layers[0]);w.auto_fix.click();settle()
            check(kind+' Auto Fix is repeatable and includes separate color-noise controls',w.photo.layers[0]==first and w.color_denoise.isVisible())
            w.undo_edit();settle();w.undo_edit();settle()
            check(kind+' Auto Fix undoes to the exact prior document',w.edit_snapshot()==snapshot)
            shot(kind+'-main');w.photo_settings.open_settings();shot(kind+'-settings',w.photo_settings);w.photo_settings.hide();w.dirty=False
        from app.services.cropping import CropRegion
        w.open_cropper(load_source=False);crop=w.cropper;crop.current_path=w.tray.import_source(cards[0]);crop.current_image=Image.open(crop.current_path).convert('RGBA');width,height=crop.current_image.size
        crop.regions=[CropRegion([(0,0),(width//2-1,0),(width//2-1,height-1),(0,height-1)]),CropRegion([(width//2,0),(width-1,0),(width-1,height-1),(width//2,height-1)])];crop.refresh_regions();settle();count=len(w.tray.items)
        check('Cropper shows icon thumbnails and fits the page',crop.region_list.count()==2 and not crop.region_list.item(0).text() and w.shell.workspace_scroll.verticalScrollBar().maximum()==0)
        w.studio.import_customer.setText('Customer: A long customer name must never cover the Crop button');settle()
        header=[crop.header.itemAt(i).widget() for i in range(crop.header.count())];header=[item for item in header if item and item.isVisible()]
        check('Crop header remains inside the page without overlapping actions',all(crop.rect().contains(item.geometry()) for item in header) and all(not item.geometry().intersects(second.geometry()) for i,item in enumerate(header) for second in header[i+1:]))
        QTest.mouseClick(crop.crop_button,Qt.LeftButton);settle()
        check('Blue Crop saves all regions and opens Photo Library',len(w.tray.items)==count+2 and w.stack.currentWidget() is w.studio.library)
        w.shell.open_settings();settle()
        from app.credits import AUTHOR,WEBSITE,EMAIL,DEVELOPMENT_CREDIT
        credits=w.shell.preferences.findChild(QLabel,'appCredits')
        check('About includes the owner, website, contact and Codex credit',credits is not None and all(text in credits.text() for text in (AUTHOR,WEBSITE,EMAIL,DEVELOPMENT_CREDIT)))
        check('Every simulated input remains byte-for-byte unchanged',all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in hashes.items()))
        check('Main and library databases retain integrity',w.db.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and w.tray.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
        ok=True
    except Exception:errors.append(traceback.format_exc())
    finally:
        if w:
            end=time.monotonic()+90
            while w.busy and time.monotonic()<end:app.processEvents();time.sleep(.01)
            for doc in (w.shell.copy,w.shell.nid):
                if doc.preview_dialog:doc.preview_dialog.close()
                doc.advanced_settings.hide();doc.dirty=False;doc.simple_inflight=False
            w.photo_settings.hide();w.timer.stop();w.invalidate_autosave();w.dirty=False;w.close();app.processEvents()
        HardwareProcess.start=old_start;QMessageBox.question=old_question;QMessageBox.warning=old_warning
    result=dict(ok=ok,version=VERSION,checks=checks,errors=errors,screenshots=screens,seconds=round(time.monotonic()-started,2),platform=app.platformName(),scale=os.environ.get('QT_SCALE_FACTOR','1'),physical_scanning=False,physical_printing=False)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));return 0 if ok else 1
