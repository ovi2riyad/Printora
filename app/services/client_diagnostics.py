"""Opt-in native release checks; no physical scan or print submission."""
import os,json,time,traceback
from pathlib import Path

def verify_client(destination):
    base=os.environ.get('LOCALAPPDATA')
    if os.environ.get('PRINTORA_CLIENT_VERIFY')!='1' or not base:raise ValueError('Use PRINTORA_CLIENT_VERIFY=1 and fresh isolated LOCALAPPDATA.')
    root=Path(base)/'StudioPhotoMaker'
    if root.exists() and any(root.iterdir()):raise ValueError('Client verification refuses existing app data.')
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtTest import QTest
    from PIL import Image,ImageDraw
    from app.ui.studio_window import StudioWindow
    from app.ui.hardware_process import HardwareProcess
    from app.services import user_folders
    from app.models.domain import Layer
    from app.services.hardware import new_scan_folder
    app=QApplication.instance() or QApplication([]);out=Path(destination).resolve();out.mkdir(parents=True,exist_ok=True);checks=[];w=None;started=time.monotonic();old_start=HardwareProcess.start;old_question=QMessageBox.question;old_warning=QMessageBox.warning;errors=[];requests=[]
    HardwareProcess.start=lambda self,*args:requests.append(args)
    QMessageBox.question=lambda *a:QMessageBox.Discard
    QMessageBox.warning=lambda *a:errors.append(str(a[-1]))
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append(name)
    def settle():
        limit=time.monotonic()+45
        while w.busy or w.timer.isActive():
            app.processEvents();time.sleep(.01)
            if time.monotonic()>limit:raise TimeoutError('GUI worker')
        for _ in range(12):app.processEvents()
        if errors:raise RuntimeError('; '.join(errors))
    def shot(name):settle();w.grab().save(str(out/(name+'.png')))
    result={}
    try:
        w=StudioWindow();w.show();settle();w.setFixedSize(1366,768);settle()
        check('Native Windows Qt',app.platformName()=='windows')
        check('Toolbar import group precedes output group',list(w.shell.toolbar_actions)==['import','scan','files','library','save','image','pdf','print']);shot('dashboard')
        pairs=[(w.stack.widget(1),w.editor_panel),(w.stack.widget(2),w.sheet_panel),(w.cropper,w.cropper.properties_panel),(w.hardware.scan_dialog,w.hardware.scan_dialog.settings_panel),(w.shell.copy,w.shell.copy.controls_panel),(w.shell.copy,w.shell.copy.pages_panel),(w.shell.nid,w.shell.nid.controls_panel),(w.shell.nid,w.shell.nid.pages_panel),(w.studio.multi,w.studio.multi.controls_panel)]
        for page,panel in pairs:
            w.stack.setCurrentWidget(page);settle()
            panel.set_mode('icons');settle();collapsed=panel.size().width()<=52 and panel.content.isHidden()
            panel.set_mode('small');settle();small=not panel.content.isHidden()
            panel.set_mode('large');settle()
            check(panel.key+' panel modes and persistence',collapsed and small and w.db.get('panel_layout')[panel.key]['mode']=='large')
        w.start_workflow('portrait');source=out/'synthetic-portrait.png';im=Image.new('RGB',(360,480),'#ADD8E6');draw=ImageDraw.Draw(im);draw.ellipse((110,55,250,210),fill='#cb9271');draw.rounded_rectangle((60,200,300,500),50,fill='#24395a');im.save(source)
        original=source.read_bytes();w.photo.layers=[Layer(str(source))];w.sync_controls();w.schedule_preview();settle();shot('portrait-large')
        w.editor_panel.set_mode('small');settle();scroll=w.editor_tabs.widget(0)
        check('Small controls have no horizontal clipping',scroll.widget().size().width()<=scroll.viewport().size().width());shot('portrait-small')
        w.editor_panel.set_mode('icons');w.shell.navigation_panel.set_mode('icons');settle();shot('portrait-icons')
        check('Navigation icons retain names as tooltips',all(not w.shell.navigation.item(i).text() and w.shell.navigation.item(i).toolTip() for i in range(13)))
        w.shell.navigation_panel.set_mode('large');w.editor_panel.set_mode('large');settle()
        split=w.shell.body_splitter;handle=split.handle(1);before=split.sizes()[0];point=handle.rect().center();QTest.mousePress(handle,Qt.LeftButton,Qt.NoModifier,point);QTest.mouseMove(handle,point+QPoint(60,0),40);QTest.mouseRelease(handle,Qt.LeftButton,Qt.NoModifier,point+QPoint(60,0));settle()
        check('Native divider drag persists width',split.sizes()[0]>before and w.db.get('panel_layout')['navigation']['width']==w.shell.navigation_panel.size().width())
        for kind in user_folders.KINDS:
            actual=user_folders.folder(w.db,kind);check(kind+' defaults inside isolated Documents',actual.is_relative_to(Path(base)/'Documents'/'Printora'))
        custom=out/'custom-scans';w.db.set('scans_folder',str(custom));acquisition=new_scan_folder(user_folders.folder(w.db,'scans'),direct=True)
        check('Custom scan destination creates unique operation directory',acquisition.parent==custom and acquisition.is_dir())
        check('Folder changes preserve original bytes',source.read_bytes()==original)
        w.invalidate_autosave();w.dirty=False;w.shell.open_settings();settle();settings=w.shell.preferences
        check('Single recipe manager and working folder settings',not any(settings.tabs.tabText(i)=='Profiles' for i in range(settings.tabs.count())) and all(k in settings.fields for k in ('input_folder','output','scans_folder','backups_folder')))
        settings.tabs.setCurrentIndex(next(i for i in range(settings.tabs.count()) if settings.tabs.tabText(i)=='Folders'));w.setFixedSize(1050,740);settle();shot('folders-1050')
        check('Compact toolbar keeps accessible icons',w.shell.action_toolbar.toolButtonStyle()==Qt.ToolButtonIconOnly)
        check('No scanner acquisition or printer submission',not any(len(r)>1 and isinstance(r[1],dict) and r[1].get('action') in ('scan','print') for r in requests))
        result=dict(passed=True,checks=checks,seconds=round(time.monotonic()-started,2),platform=app.platformName(),scale=os.environ.get('QT_SCALE_FACTOR','1'))
    except Exception as error:result=dict(passed=False,checks=checks,error=repr(error),traceback=traceback.format_exc());traceback.print_exc()
    finally:
        if w:
            w.timer.stop();w.pool.waitForDone();w.invalidate_autosave();w.dirty=False;w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.hardware.shutdown();w.close();app.processEvents()
        HardwareProcess.start=old_start;QMessageBox.question=old_question;QMessageBox.warning=old_warning
        (out/'result.json').write_text(json.dumps(result,indent=2),'utf-8');print(json.dumps(result,indent=2),flush=True)
    return 0 if result.get('passed') else 1
