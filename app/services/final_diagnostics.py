"""Explicit isolated software acceptance. Never calls scanner acquisition or printing."""
import os,json,time,hashlib,traceback
from pathlib import Path

def verify_final(destination):
    base=os.environ.get('LOCALAPPDATA')
    if os.environ.get('PRINTORA_FINAL_VERIFY')!='1' or not base:raise ValueError('Use PRINTORA_FINAL_VERIFY=1 and a fresh isolated LOCALAPPDATA')
    root=Path(base)/'StudioPhotoMaker'
    if root.exists() and any(root.iterdir()):raise ValueError('Final diagnostic refuses existing application data')
    from PIL import Image,ImageDraw
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtCore import Qt
    from pypdf import PdfReader
    from app.ui.studio_window import StudioWindow
    from app.services.documents import DocumentSession
    from app.services.pdf import export_pdf
    from app.services.layout import validate_layout
    from app.services.storage import backup_data,prepare_restore,discard_restore
    from app.version import VERSION
    out=Path(destination);out.mkdir(parents=True,exist_ok=True);start=time.monotonic();checks=[];errors=[];w=None
    app=QApplication.instance() or QApplication([]);old_warning=QMessageBox.warning
    QMessageBox.warning=lambda *args:errors.append(str(args[-1]))
    def check(name,condition=True):
        if not condition:raise AssertionError(name)
        checks.append(name)
    def wait():
        end=time.monotonic()+30
        while w.busy and time.monotonic()<end:app.processEvents();time.sleep(.01)
        if w.busy:raise RuntimeError('Image worker timed out')
        app.processEvents()
    try:
        w=StudioWindow();w.show();app.processEvents();check('Native shell opens with thirteen workspaces',w.shell.navigation.count()==13)
        for theme in ('Light','Dark','System'):
            w.shell.set_theme(theme)
            for size in ((1050,740),(1366,768)):
                available=app.primaryScreen().availableGeometry();w.resize(min(size[0],available.width()-20),min(size[1],available.height()-50));app.processEvents();w.grab().save(str(out/f'dashboard-{theme}-{size[0]}.png'))
            check(theme+' controls remain reachable in available logical viewport',w.size().width()<=available.width() and w.size().height()<=available.height())
            check(theme+' theme applies',w.property('themeMode') in ('Light','Dark'))
        fixtures=out/'synthetic-inputs';fixtures.mkdir(exist_ok=True);originals={}
        for side,color in [('Front','#aacadd'),('Back','#ddc9a5')]:
            path=fixtures/(side+'.png');image=Image.new('RGB',(1000,700),'white');draw=ImageDraw.Draw(image)
            draw.rectangle((70,80,930,620),fill=color,outline='black',width=4);draw.text((200,250),'FICTIONAL TEST CARD / NOT VALID ID',fill='black');image.save(path,dpi=(300,300));originals[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        copy=w.shell.copy;w.shell.open(copy);copy.import_files(paths=list(originals));wait();check('Existing documents import without library entries',len(copy.session.pages)==2 and not w.tray.items)
        copy.fields['copies'].setValue(3);copy.fields['brightness'].setValue(1.1);copy.color.setCurrentText('gray');copy.scale_mode.setCurrentIndex(copy.scale_mode.findData('fit'))
        job=copy.make_job();validate_layout(job);export_pdf(job,out/'copy.pdf');check('Three collated copies of two input pages',job.page_count==6 and len(PdfReader(out/'copy.pdf').pages)==6)
        copy.session.export_image(copy.session.pages[0],copy.settings(),out/'processed.png');check('Processed image exports',Image.open(out/'processed.png').getpixel((0,0))[0]==Image.open(out/'processed.png').getpixel((0,0))[1])
        copy.save_session();saved=copy.session.root/'session.json';check('Explicit saved document snapshot reopens',len(DocumentSession.open(saved).pages)==2)
        copy.grab().save(str(out/'quick-copy.png'))
        nid=w.shell.nid;w.shell.open(nid);nid.import_files(paths=list(originals));wait()
        from app.services.documents import detect_card
        for page in nid.session.pages:
            with Image.open(page.source) as image:page.points=detect_card(image)
            check(page.label+' boundary proposed',len(page.points)==4);nid.reviewed.add(id(page))
        nid.fields['copies'].setValue(2);job=nid.make_job();export_pdf(job,out/'nid-copy.pdf')
        check('Two front/back pairs keep one pair per A4 page',len(job.placements)==4 and job.page_count==2 and all(job.placements[i].page==job.placements[i+1].page for i in (0,2)))
        check('NID Front and Back share the paper horizontal center',all(abs(p.x+p.width/2-105)<.001 for p in job.placements))
        check('NID Front and Back center vertically as a complete group',all(abs((job.placements[i].y+job.placements[i+1].y+job.placements[i+1].height)/2-148.5)<.001 for i in (0,2)))
        check('Card placement preserves the reviewed source proportions',abs(job.photos[0].width/job.photos[0].height-860/540)<.03)
        nid.refresh();wait();nid.grab().save(str(out/'nid-review.png'))
        nid.rotate();wait();check('Rotation is nondestructive',nid.current().rotation==90)
        nid.dirty=False;w.shell.open(w.hardware.scan_dialog);app.processEvents();w.grab().save(str(out/'scan-studio.png'))
        w.studio.show(w.studio.tools);app.processEvents();w.grab().save(str(out/'studio-tools.png'));check('Tools gallery retains usable minimum height',w.studio.tools.gallery.height()>=240)
        w.shell.open_recipes();app.processEvents();w.grab().save(str(out/'recipes.png'))
        w.shell.open_settings();app.processEvents();w.grab().save(str(out/'settings.png'))
        archive=out/'verified-backup.zip';backup_data(root,archive);stage=prepare_restore(archive,out/'restored-data');discard_restore(stage,out/'restored-data');check('Saved session backup verifies and stages at another path')
        for conn in (w.db.conn,w.tray.conn):check('SQLite integrity and foreign keys',conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not conn.execute('PRAGMA foreign_key_check').fetchall())
        check('Input bytes unchanged',all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in originals.items()))
        check('Card/copy workflows create no customers, orders or prepared photos',not w.tray.items and w.db.conn.execute('SELECT COUNT(*) FROM customers').fetchone()[0]==0 and w.db.conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0)
        check('No unexpected recovery dialogs',not errors)
        result=dict(passed=True,version=VERSION,checks=checks,errors=errors,physical_acquisition=False,physical_print=False,scale=os.environ.get('QT_SCALE_FACTOR','1'),screen=[app.primaryScreen().size().width(),app.primaryScreen().size().height()])
    except Exception as error:result=dict(passed=False,checks=checks,error=repr(error),traceback=traceback.format_exc(),errors=errors)
    finally:
        QMessageBox.warning=old_warning
        if w:
            wait();w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.dirty=False;w.timer.stop();w.invalidate_autosave();w.close();app.processEvents()
    result['seconds']=round(time.monotonic()-start,2);(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
