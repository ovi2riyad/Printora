"""Release UI panels, working folders and installer build contract."""
import json
from pathlib import Path
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog,QWidget
from app.core.database import Database
from app.services import user_folders

@pytest.fixture
def window(tmp_path,monkeypatch):
    from app.ui.hardware_process import HardwareProcess
    from app.ui.studio_window import StudioWindow
    app=QApplication.instance() or QApplication([])
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user-data'))
    monkeypatch.setattr(user_folders,'documents_directory',lambda:tmp_path/'Redirected Documents')
    monkeypatch.setattr(HardwareProcess,'start',lambda *a:None)
    w=StudioWindow();w.show();app.processEvents()
    yield w
    w.timer.stop();w.pool.waitForDone();app.processEvents();w.invalidate_autosave();w.dirty=False;w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.hardware.shutdown();w.close();w.deleteLater()
    from PySide6.QtCore import QCoreApplication,QEvent
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()

def settle():
    for _ in range(12):QApplication.processEvents()

@pytest.mark.parametrize('name',['navigation_panel','editor_panel','sheet_panel','cropper_panel','scan_panel','copy_controls','copy_pages','nid_controls','nid_pages','multi_controls'])
def test_each_panel_modes_and_restore(window,name):
    w=window;panels={'navigation_panel':w.shell.navigation_panel,'editor_panel':w.editor_panel,'sheet_panel':w.sheet_panel,'cropper_panel':w.cropper.properties_panel,'scan_panel':w.hardware.scan_dialog.settings_panel,'copy_controls':w.shell.copy.controls_panel,'copy_pages':w.shell.copy.pages_panel,'nid_controls':w.shell.nid.controls_panel,'nid_pages':w.shell.nid.pages_panel,'multi_controls':w.studio.multi.controls_panel}
    panel=panels[name];panel.set_mode('icons');settle()
    assert panel.maximumWidth()==52
    assert panel.content.isHidden()==(not panel.navigation)
    panel.set_mode('small');settle();assert not panel.content.isHidden()
    panel.set_mode('large');settle();assert panel.mode=='large'
    saved=w.db.get('panel_layout');assert saved[panel.key]['mode']=='large'
    from app.ui.panels import AdaptivePanel
    restored=AdaptivePanel(QWidget(),w.db,panel.key,'Restored')
    assert restored.mode=='large' and restored.saved_width==saved[panel.key]['width']

def test_navigation_icon_text_and_real_splitter_drag(window):
    w=window;panel=w.shell.navigation_panel
    panel.set_mode('icons');settle();assert all(not w.shell.navigation.item(i).text() for i in range(13))
    panel.set_mode('large');settle();assert all(w.shell.navigation.item(i).text() for i in range(13))
    split=w.shell.body_splitter;handle=split.handle(1);before=split.sizes()[0];start=handle.rect().center()
    QTest.mousePress(handle,Qt.LeftButton,Qt.NoModifier,start);QTest.mouseMove(handle,start+QPoint(75,0),30);QTest.mouseRelease(handle,Qt.LeftButton,Qt.NoModifier,start+QPoint(75,0));settle()
    assert split.sizes()[0]>before and w.db.get('panel_layout')['navigation']['width']==panel.size().width()

@pytest.mark.parametrize('raw',['[]','{"editor":{"mode":"wrong","width":350}}','{"editor":{"mode":"large","width":NaN}}','{"editor":null}'])
def test_invalid_panel_preferences_recover_without_rewriting(window,raw):
    w=window;w.db.conn.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('panel_layout',raw));w.db.conn.commit()
    assert w.db.get('panel_layout',{})=={}
    assert w.db.conn.execute('SELECT value FROM config WHERE key=?',('panel_layout',)).fetchone()[0]==raw

def test_user_folders_redirected_defaults_custom_and_no_asset_move(window,tmp_path):
    w=window
    for kind,name in user_folders.KINDS.items():
        assert user_folders.folder(w.db,kind)==tmp_path/'Redirected Documents'/'Printora'/name
    original=tmp_path/'original.jpg';original.write_bytes(b'original bytes')
    target=tmp_path/'Custom Output';w.db.set('output',str(target))
    assert user_folders.output_path(w.db,'some/name.pdf')==str(target/'some-name.pdf')
    assert original.read_bytes()==b'original bytes'
    fresh=Database(w.db.path);assert user_folders.folder(fresh,'output')==target;fresh.conn.close()

def test_file_dialogs_use_configured_folders(window,tmp_path,monkeypatch):
    w=window;source=tmp_path/'Input';destination=tmp_path/'Output';w.db.set('input_folder',str(source));w.db.set('output',str(destination));captured=[]
    monkeypatch.setattr(QFileDialog,'getOpenFileNames',lambda *a,**k:(captured.append(a[2]) or [],''))
    w.cropper.import_sources();w.shell.copy.import_files();assert captured==[str(source),str(source)]
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(captured.append(a[2]) or '', ''))
    from PIL import Image
    photo=tmp_path/'page.png';Image.new('RGB',(100,150),'white').save(photo);w.shell.copy.session.import_image(photo,dpi=300);w.shell.copy.refresh()
    import time
    limit=time.monotonic()+20
    while w.busy and time.monotonic()<limit:QApplication.processEvents();time.sleep(.005)
    w.shell.copy.export_image();assert Path(captured[-1]).parent==destination

def test_settings_folders_and_no_duplicate_profile_manager(window,tmp_path):
    w=window;w.shell.open_settings();settings=w.shell.preferences
    assert settings.tabs.indexOf(settings.tabs.widget(1))>=0
    assert sum(settings.tabs.tabText(i)=='Profiles' for i in range(settings.tabs.count()))==0
    for kind in user_folders.KINDS:
        key='output' if kind=='output' else kind+'_folder';settings.fields[key].setText(str(tmp_path/kind))
    settings.save()
    assert user_folders.folder(w.db,'scans')==tmp_path/'scans'

def test_build_uses_requested_payload_and_installer_default(monkeypatch,tmp_path):
    from scripts import build_release
    calls=[];target=tmp_path/'release'/'StudioPhotoMaker'
    monkeypatch.setattr(build_release,'make_icon',lambda p:None)
    monkeypatch.setattr(build_release,'prepare_payload',lambda p:Path(p))
    monkeypatch.setattr(build_release.subprocess,'run',lambda args,**kw:calls.append(args))
    monkeypatch.setattr(build_release,'compile_installer',lambda *a:calls.append(('installer',*a)))
    monkeypatch.setattr('sys.argv',['build_release','--payload',str(target),'--output',str(tmp_path/'Setup')])
    build_release.main();args=calls[0]
    assert args[args.index('--distpath')+1]==str(target.parent)
    assert calls[1][0]=='installer' and Path(calls[1][1])==target

def test_installer_target_identity_and_no_user_data_delete():
    source=(Path(__file__).resolve().parents[1]/'installer/Printora.iss').read_text()
    assert 'DefaultDirName=C:\\Printora' in source
    assert '4F077504-7244-4BEB-B290-FE8758932B47' in source
    assert '[UninstallDelete]' not in source and '{commondesktop}' in source and '{commonprograms}' in source

@pytest.mark.parametrize('value',['relative/folder','', '\x00bad'])
def test_invalid_folder_preferences_rejected(window,value):
    from app.services.preferences import validate_preferences,default_preferences
    values=default_preferences();values['scans_folder']=value
    with pytest.raises(ValueError):validate_preferences(values)

@pytest.mark.parametrize('kind,side',[('copy','Page'),('nid','Front')])
def test_document_scan_retains_documents_original_after_clear(window,tmp_path,monkeypatch,kind,side):
    from PIL import Image
    import time
    w=window;page=getattr(w.shell,kind);w.stack.setCurrentWidget(page)
    scans=user_folders.folder(w.db,'scans');source=scans/'verified-original.png';Image.new('RGB',(120,160),'white').save(source);before=source.read_bytes()
    monkeypatch.setattr(w.hardware.scan_dialog,'scan_now',lambda:None)
    page.scan(side);assert w.hardware.scan_dialog.folder_root is None
    callback=w.hardware.scan_dialog.completion_callback;w.hardware.scan_dialog.completion_callback=None
    callback(dict(original=str(source),driver={'dpi':300}))
    deadline=time.monotonic()+30
    while w.busy and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
    assert len(page.session.pages)==1
    asset=Path(page.session.pages[0].source);assert asset.is_relative_to(page.session.root) and asset.read_bytes()==before
    assert page.clear(confirm=False) and source.read_bytes()==before

def test_unwritable_working_folder_is_reported_without_overwriting_file(window,tmp_path):
    path=tmp_path/'existing-file';path.write_bytes(b'keep');window.db.set('scans_folder',str(path));messages=[]
    assert user_folders.dialog_folder(window.db,'scans',messages.append)==''
    assert messages and 'Settings' in messages[0] and path.read_bytes()==b'keep'

def test_toolbar_routes_active_document_and_disables_irrelevant_exports(window,monkeypatch):
    w=window;calls=[];assert not w.shell.toolbar_actions['pdf'].isEnabled()
    page=w.shell.copy;monkeypatch.setattr(page,'export',lambda:calls.append('pdf'));monkeypatch.setattr(page,'export_image',lambda:calls.append('image'))
    w.stack.setCurrentWidget(page);settle();w.shell.toolbar_actions['pdf'].trigger();w.shell.toolbar_actions['image'].trigger();assert calls==['pdf','image']
    w.home();assert not w.shell.toolbar_actions['image'].isEnabled()

def test_editor_pdf_action_opens_review_before_export(window,monkeypatch):
    w=window;w.start_workflow('portrait');calls=[]
    monkeypatch.setattr(w,'show_print',lambda:calls.append('review'));monkeypatch.setattr(w,'print_pdf',lambda:calls.append('export'))
    w.shell.toolbar_actions['pdf'].trigger();assert calls==['review']
    w.stack.setCurrentIndex(2);w.shell.toolbar_actions['pdf'].trigger();assert calls==['review','export']

@pytest.mark.parametrize('kind',['panel','workspace'])
def test_pending_resize_callbacks_are_canceled_with_deleted_widgets(monkeypatch,kind):
    import sys
    from PySide6.QtCore import QCoreApplication,QEvent
    from PySide6.QtWidgets import QStackedWidget
    app=QApplication.instance() or QApplication([]);errors=[];monkeypatch.setattr(sys,'excepthook',lambda *args:errors.append(args))
    if kind=='panel':
        from app.ui.panels import AdaptivePanel,splitter
        panel=AdaptivePanel(QWidget(),None,'temporary','Temporary');widget=splitter(QWidget(),panel)
    else:
        from app.ui.shell import WorkspaceScroll
        stack=QStackedWidget();stack.addWidget(QWidget());widget=WorkspaceScroll(stack);widget.schedule_fit()
    widget.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    for _ in range(10):app.processEvents()
    assert not errors

@pytest.mark.parametrize('width,minimum',[(180,140),(290,240),(350,280),(400,350),(550,420)])
def test_small_preset_is_smaller_for_narrow_and_wide_panels(monkeypatch,width,minimum):
    from app.ui.panels import AdaptivePanel
    app=QApplication.instance() or QApplication([]);panel=AdaptivePanel(QWidget(),None,'preset','Preset',default_width=width,minimum_width=minimum);targets=[]
    monkeypatch.setattr(panel,'resize_panel',targets.append);panel.set_mode('small')
    assert minimum<=targets[-1]<width
    panel.deleteLater();app.processEvents()
