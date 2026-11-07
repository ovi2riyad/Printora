"""PA-002/PA-001 regressions using disposable SQLite data and actual Qt events."""
import json
import os
import sqlite3
import logging
import time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox,QDialog,QListWidget
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from app.core.database import Database
from app.ui.studio_window import StudioWindow
from app.models.domain import Job,Photo,Layer


def qt_wait(milliseconds):
    # Yield Python as well as Qt so QRunnable rendering can finish normally.
    end=time.monotonic()+milliseconds/1000
    while time.monotonic()<end:
        QApplication.processEvents();time.sleep(.01)


@pytest.mark.parametrize('raw,expected',[
    ('["#ADD8E6","red","#123456"]',['#ADD8E6','red','#123456']),
    ('[]',[]), ('{broken-json',[]), ('{}',[]), ('null',[]), ('42',[]),
    ('"#123456"',[]), ('true',[]),
    ('["invalid",17,null,{},[],false]',[]),
    ('["#ADD8E6",["red"],{"color":"blue"},"#000000","no-color"]',['#ADD8E6','#000000']),
])
def test_pa002_color_history(raw,expected,tmp_path,caplog):
    db=Database(tmp_path/'studio.db')
    with db.conn:db.conn.execute('INSERT INTO config VALUES(?,?)',('recent_colors',raw))
    with caplog.at_level(logging.WARNING):
        assert db.get('recent_colors',[])==expected
        assert db.get('recent_colors',[])==expected
    assert db.conn.execute('SELECT value FROM config WHERE key="recent_colors"').fetchone()[0]==raw
    assert len([r for r in caplog.records if 'recent_colors' in r.message])<=1
    assert len(db.preference_diagnostics)<=1
    db.conn.close()


def test_pa002_missing_defaults_and_valid_nested_preferences(tmp_path):
    db=Database(tmp_path/'studio.db')
    assert db.get('recent_colors',[])==[] and not db.preference_diagnostics
    values=dict(recent_colors=['#ADD8E6'],quantity=7,show_guides=False,
        recipe_usage={'recipe':3},composition_presets={'Studio':{'top':3,'mode':'balanced','horizontal':.5}},
        calibrations={'Printer':1.01},printer_profiles={'Printer':dict(measured_width=100,measured_height=99,driver_x=1,driver_y=100/99)})
    for key,value in values.items():db.set(key,value);assert db.get(key)==value
    assert not db.preference_diagnostics
    db.conn.close()


@pytest.mark.parametrize('key,raw,expected',[
    ('show_guides','[]',True),('default_workflow','{}','dashboard'),
    ('portrait_width','"wide"',42.),('quantity','true',4),('dpi','NaN',300),
    ('background','{"red":1}','#ADD8E6'),('output','[]',None),('model_dir','{}',None),
    ('recipe_usage','{"ok":2,"bad":{},"other":true}',{'ok':2}),
    ('composition_presets','{"ok":{"top":3},"bad":{"horizontal":[]}}',{'ok':{'top':3}}),
    ('calibrations','{"ok":1,"bad":null}',{'ok':1}),
    ('printer_profiles','{"bad":{"driver_x":[]}}',{}),
])
def test_pa002_optional_types_and_nested_entries(key,raw,expected,tmp_path):
    from app.services.optional_preferences import OPTIONAL_DEFAULTS
    db=Database(tmp_path/'studio.db')
    with db.conn:db.conn.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(key,raw))
    assert db.get(key)==(OPTIONAL_DEFAULTS[key] if expected is None else expected)
    assert len(db.preference_diagnostics)==1
    assert db.conn.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()[0]==raw
    db.conn.close()


def rows_snapshot(conn):
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in tables}


@pytest.mark.parametrize('raw',['["#123456"]','{broken-json','["red",[],null,"bad"]'])
def test_pa002_source_startup_reopen_and_data_preservation(raw,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=StudioWindow()
    source=tmp_path/'original.png';Image.new('RGB',(60,80),'orange').save(source)
    managed=w.tray.import_source(source);item=w.tray.add('Synthetic portrait',Image.open(source),managed)
    customer=w.studio.customers.save(dict(name='Synthetic customer',mobile='01700000000'))
    w.studio.customers.assign_photos(customer['id'],[item.id],w.tray)
    job=Job(photos=[Photo(layers=[Layer(str(item.asset))])]);w.db.save_job(job)
    w.studio.orders.create(job,customer['id'])
    w.db.set('quantity',7);w.db.set('unrelated_option',{'retained':[1,2,3]})
    with w.db.conn:w.db.conn.execute('INSERT INTO config VALUES(?,?)',('recent_colors',raw))
    main_before=rows_snapshot(w.db.conn);library_before=rows_snapshot(w.tray.conn)
    source_bytes=source.read_bytes();asset_bytes=item.asset and open(item.asset,'rb').read()
    w.close();app.processEvents()
    for _ in range(2):
        w=StudioWindow();w.show();app.processEvents()
        assert [w.editor_tools.recent.itemText(i) for i in range(w.editor_tools.recent.count())]==(['#123456'] if raw.startswith('["#') else ['red'] if raw.startswith('["red') else [])
        assert w.db.get('quantity')==7
        assert rows_snapshot(w.db.conn)==main_before
        assert rows_snapshot(w.tray.conn)==library_before
        for conn in (w.db.conn,w.tray.conn):
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert source.read_bytes()==source_bytes and open(item.asset,'rb').read()==asset_bytes
        w.close();app.processEvents()


@pytest.fixture
def editor(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=StudioWindow();w.show();app.processEvents()
    messages=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:messages.append(a[-1]))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Discard)
    source=tmp_path/'subject.png';Image.new('RGB',(60,80),'orange').save(source)
    assert w.start_workflow('portrait')
    w.photo.layers=[Layer(str(source))];w.sync_controls();assert w.save_job()
    yield w,app,messages
    deadline=time.monotonic()+10
    while w.busy and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
    if w.isVisible():w.dirty=False;w.close();app.processEvents()


def test_pa001_dashboard_discard_real_timeout_and_later_explicit_save(editor):
    w,app,errors=editor;id=w.job.id;before=w.db.load_job(id).to_dict()
    w.set_color('background','#112233');stale=w._autosave_callback
    w.home();assert w.stack.currentIndex()==0 and not w.dirty
    assert w.photo.background=='#ADD8E6'
    QTimer.singleShot(0,stale);qt_wait(2500)
    assert w.db.load_job(id).to_dict()==before
    # A later Save/Ctrl+S cannot resurrect the discarded model.
    assert w.save_job();assert w.db.load_job(id).to_dict()==before
    assert not errors


@pytest.mark.parametrize('route',['library','customers','orders','multi','tools','cropper','new_workflow','open_job','saved_jobs_dialog','import','close'])
def test_pa001_discard_navigation_routes(editor,monkeypatch,route):
    w,app,errors=editor;id=w.job.id;before=w.db.load_job(id).to_dict();db_path=w.db.path
    other=Job(name='Other',photos=[Photo(layers=[Layer(w.photo.layers[0].source)])]);w.db.save_job(other)
    w.set_color('background','#112233');stale=w._autosave_callback
    if route in ('library','customers','orders','multi','tools'):
        page={'library':w.studio.library,'customers':w.studio.customer_page,'orders':w.studio.order_page,'multi':w.studio.multi,'tools':w.studio.tools}[route]
        w.studio.show(page);assert w.stack.currentWidget() is page
    elif route=='cropper':assert w.open_cropper(load_source=False)
    elif route=='new_workflow':assert w.start_workflow('joint');assert w.mode=='joint'
    elif route=='open_job':w.studio.open_job(other.id);assert w.job.id==other.id
    elif route=='saved_jobs_dialog':
        def select_saved(dialog):
            dialog.findChild(QListWidget).setCurrentRow([r[0] for r in w.db.jobs()].index(other.id));return 1
        monkeypatch.setattr(QDialog,'exec',select_saved)
        w.open_jobs();assert w.job.id==other.id
    elif route=='import':
        called=[];monkeypatch.setattr(w.cropper,'import_sources',lambda **k:called.append(k));w.import_to_cropper(paths=['placeholder']);assert called
    else:w.close();assert not w.isVisible()
    QTimer.singleShot(0,stale);qt_wait(70)
    conn=sqlite3.connect(db_path)
    assert json.loads(conn.execute('SELECT payload FROM jobs WHERE id=?',(id,)).fetchone()[0])==before
    assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert conn.execute('PRAGMA foreign_key_check').fetchall()==[];conn.close()
    assert not errors


def test_pa001_new_unsaved_discard_unloads_and_never_creates_row(editor):
    w,app,errors=editor
    w.start_workflow('portrait');id=w.job.id
    w.photo.layers=[Layer(str(Path(w.db.path).parent.parent/'subject.png'))]
    w.set_color('background','#112233');stale=w._autosave_callback
    w.home();assert w.photo is None and not w.dirty and not w.undo
    assert not w.save_job()
    QTimer.singleShot(0,stale);qt_wait(2500)
    assert not w.db.conn.execute('SELECT 1 FROM jobs WHERE id=?',(id,)).fetchone()
    assert not errors


def test_pa001_cancel_preserves_edits_and_resumes_actual_autosave(editor,monkeypatch):
    w,app,errors=editor;id=w.job.id
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Cancel)
    w.set_color('background','#112233');w.home()
    assert w.stack.currentIndex()==1 and w.dirty and w.photo.background=='#112233'
    assert w.autosave.isActive()
    qt_wait(2800)
    assert not w.dirty and w.db.load_job(id).photos[0].background=='#112233'
    assert not errors


def test_pa001_save_prompt_explicit_save_and_autosave_after_reopen(editor,monkeypatch):
    w,app,errors=editor;id=w.job.id
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Save)
    w.set_color('background','#112233');stale=w._autosave_callback;w.home()
    assert not w.dirty and not w.autosave.isActive()
    assert w.db.load_job(id).photos[0].background=='#112233'
    w.studio.open_job(id);w.set_color('background','#223344')
    QTimer.singleShot(0,stale);qt_wait(2800)
    assert not w.dirty and w.db.load_job(id).photos[0].background=='#223344'
    assert not errors


def test_pa001_save_failure_keeps_dirty_and_blocks_navigation(editor,monkeypatch):
    w,app,errors=editor;id=w.job.id
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Save)
    w.set_color('background','#112233')
    def fail(job):raise sqlite3.OperationalError('synthetic read-only database')
    with monkeypatch.context() as patch:
        patch.setattr(w.db,'save_job',fail);w.home()
    assert w.dirty and w.stack.currentIndex()==1 and w.autosave.isActive()
    assert w.db.load_job(id).photos[0].background=='#ADD8E6'
    assert w.save_job() and not w.dirty
    assert w.db.load_job(id).photos[0].background=='#112233'
    assert len(errors)==1


def test_pa001_stale_queued_callbacks_multiple_document_switches(editor):
    w,app,errors=editor;original=w.job.id;stale=[]
    for i in range(3):
        other=Job(name=f'Other {i}',photos=[Photo(layers=[Layer(w.photo.layers[0].source)])]);w.db.save_job(other)
        w.set_color('background','#112233');stale.append(w._autosave_callback)
        w.studio.open_job(other.id)
    w.set_color('background','#334455')
    # Stale callbacks delivered AFTER the new document's own timer was armed.
    for callback in stale:QTimer.singleShot(0,callback)
    qt_wait(80)
    assert w.dirty and w.db.load_job(w.job.id).photos[0].background=='#ADD8E6'
    assert w.db.load_job(original).photos[0].background=='#ADD8E6'
    assert w.save_job();assert w.db.load_job(w.job.id).photos[0].background=='#334455'
    assert not errors


def test_pa001_already_fired_autosave_is_saved_baseline(editor):
    w,app,errors=editor;id=w.job.id
    w.set_color('background','#223344');qt_wait(2800)
    assert w.db.load_job(id).photos[0].background=='#223344'
    w.set_color('background','#112233');w.home();qt_wait(2500)
    assert w.db.load_job(id).photos[0].background=='#223344'
    assert w.photo.background=='#223344' and not errors


def test_pa001_modal_nested_event_loop_invalidates_queued_save(editor,monkeypatch):
    w,app,errors=editor;id=w.job.id
    # Restore the real native Qt question implementation, not a fake return value.
    monkeypatch.undo()
    w.set_color('background','#112233');stale=w._autosave_callback
    QTimer.singleShot(0,stale)
    def choose_discard():
        dialog=QApplication.activeModalWidget()
        assert isinstance(dialog,QMessageBox)
        QTest.mouseClick(dialog.button(QMessageBox.Discard),Qt.LeftButton)
    QTimer.singleShot(60,choose_discard)
    assert w.save_before_leave()
    assert w.photo.background=='#ADD8E6' and not w.dirty
    assert w.db.load_job(id).photos[0].background=='#ADD8E6'


def test_pa001_cropper_cancel_does_not_import_or_navigate(editor,monkeypatch):
    w,app,errors=editor;calls=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Cancel)
    monkeypatch.setattr(w.cropper,'import_sources',lambda **k:calls.append(k))
    w.set_color('background','#112233');w.import_to_cropper(paths=['placeholder'])
    assert not calls and w.stack.currentIndex()==1 and w.dirty and w.autosave.isActive()


def test_pa002_all_known_optional_preferences_malformed_at_startup(tmp_path,monkeypatch):
    from app.services.optional_preferences import OPTIONAL_DEFAULTS
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=QApplication.instance() or QApplication([]);w=StudioWindow()
    with w.db.conn:
        w.db.conn.executemany('INSERT OR REPLACE INTO config VALUES(?,?)',[(key,'{invalid-json') for key in OPTIONAL_DEFAULTS])
    w.close();app.processEvents()
    w=StudioWindow();w.show();app.processEvents()
    assert w.start_workflow('portrait') and (w.photo.width,w.photo.height)==(42,52)
    assert w.photo.background=='#ADD8E6' and w.photo.quantity==4
    assert w.db.conn.execute('SELECT COUNT(*) FROM config WHERE value=?',('{invalid-json',)).fetchone()[0]==len(OPTIONAL_DEFAULTS)
    w.dirty=False;w.close();app.processEvents()


def test_pa001_ctrl_s_and_stale_callback_cannot_save_a_later_edit(editor):
    w,app,errors=editor;id=w.job.id
    w.activateWindow();w.setFocus();app.processEvents()
    w.set_color('background','#112233');stale=w._autosave_callback
    QTest.keyClick(w,Qt.Key_S,Qt.ControlModifier)
    assert not w.dirty and w.db.load_job(id).photos[0].background=='#112233'
    w.set_color('background','#223344');QTimer.singleShot(0,stale);qt_wait(80)
    assert w.dirty and w.db.load_job(id).photos[0].background=='#112233'
    assert w.save_job() and not errors


@pytest.mark.parametrize('choice',[QMessageBox.Save,QMessageBox.Cancel])
def test_pa001_close_save_and_cancel(editor,monkeypatch,choice):
    w,app,errors=editor;id=w.job.id;path=w.db.path
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:choice)
    w.set_color('background','#112233');w.close()
    assert w.isVisible()==(choice==QMessageBox.Cancel)
    if choice==QMessageBox.Cancel:
        assert w.dirty and w.autosave.isActive()
        qt_wait(2800);assert not w.dirty
    conn=sqlite3.connect(path)
    assert json.loads(conn.execute('SELECT payload FROM jobs WHERE id=?',(id,)).fetchone()[0])['photos'][0]['background']=='#112233'
    conn.close();assert not errors


def test_pa001_session_review_adopts_new_document_and_stale_save_stays_invalid(editor):
    import copy
    w,app,errors=editor;id=w.job.id
    multi=w.studio.multi;multi.job.photos=[copy.deepcopy(w.photo)];multi.refresh();multi.table.selectRow(0)
    w.set_color('background','#112233');stale=w._autosave_callback
    multi.edit();review_id=w.job.id
    assert review_id!=id and w.photo.background=='#ADD8E6'
    w.set_color('background','#334455');QTimer.singleShot(0,stale);qt_wait(80)
    assert w.dirty and not w.db.conn.execute('SELECT 1 FROM jobs WHERE id=?',(review_id,)).fetchone()
    assert w.db.load_job(id).photos[0].background=='#ADD8E6'
    assert w.save_job() and not errors


def test_stabilization_diagnostic_refuses_normal_application_data(tmp_path,monkeypatch):
    from app.services.stabilization_diagnostics import verify_stabilization
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));monkeypatch.delenv('PRINTORA_STABILIZATION_VERIFY',raising=False)
    with pytest.raises(ValueError,match='fresh isolated'):verify_stabilization(tmp_path/'results')
    assert not (tmp_path/'StudioPhotoMaker').exists()


def test_stabilization_diagnostic_refuses_existing_data_even_with_opt_in(tmp_path,monkeypatch):
    from app.services.stabilization_diagnostics import verify_stabilization
    root=tmp_path/'StudioPhotoMaker';root.mkdir();marker=root/'retain.txt';marker.write_bytes(b'preserve')
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));monkeypatch.setenv('PRINTORA_STABILIZATION_VERIFY','1')
    with pytest.raises(ValueError,match='empty isolated'):verify_stabilization(tmp_path/'results')
    assert marker.read_bytes()==b'preserve' and list(root.iterdir())==[marker]
