"""Isolated PA-002/PA-001 acceptance for source and frozen candidate builds."""
import hashlib
import json
import os
from pathlib import Path
import time


def verify_stabilization(destination):
    # Fault injection must never run against an existing application-data folder.
    base=os.environ.get('LOCALAPPDATA')
    if os.environ.get('PRINTORA_STABILIZATION_VERIFY')!='1' or not base:
        raise ValueError('Set PRINTORA_STABILIZATION_VERIFY=1 and a fresh isolated LOCALAPPDATA for this diagnostic.')
    root=Path(base)/'StudioPhotoMaker'
    if root.exists() and any(root.iterdir()):raise ValueError('Stabilization diagnostic requires empty isolated app data.')
    from PIL import Image
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QMessageBox
    from app.ui.studio_window import StudioWindow
    from app.models.domain import Job,Photo,Layer
    app=QApplication.instance() or QApplication([])
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    checks=[];windows=[];errors=[];start=time.monotonic()
    old_warning=QMessageBox.warning
    QMessageBox.warning=lambda *args:errors.append(str(args[-1]))

    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append(name)
    def wait(milliseconds):
        end=time.monotonic()+milliseconds/1000
        while time.monotonic()<end:app.processEvents();time.sleep(.01)
    def window():
        w=StudioWindow();windows.append(w);w.show();app.processEvents();return w
    def snapshot(conn):
        names=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'config' ORDER BY name")]
        return {name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in names}
    def choose(button):
        def click():
            dialog=QApplication.activeModalWidget()
            if not isinstance(dialog,QMessageBox):raise AssertionError('Expected a real save-decision dialog')
            dialog.button(button).click()
        QTimer.singleShot(60,click)
    try:
        w=window();check('Fresh startup with missing optional preferences',not w.db.preference_diagnostics)
        source=out/'synthetic-original.png';Image.new('RGB',(120,160),'orange').save(source)
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        managed=w.tray.import_source(source);item=w.tray.add('Synthetic portrait',Image.open(source),managed)
        customer=w.studio.customers.save(dict(name='Synthetic stabilization fixture',mobile='01700000000'))
        w.studio.customers.assign_photos(customer['id'],[item.id],w.tray)
        first=Job(name='Saved baseline',photos=[Photo(layers=[Layer(item.asset)])]);w.db.save_job(first)
        second=Job(name='Next document',photos=[Photo(layers=[Layer(item.asset)])]);w.db.save_job(second)
        w.studio.orders.create(first,customer['id']);w.db.set('quantity',7)
        before=snapshot(w.db.conn);library_before=snapshot(w.tray.conn)
        for raw,colors in [('["#ADD8E6","red"]',['#ADD8E6','red']),('{broken-json',[]),('{}',[]),('["red",[],null,"invalid"]',['red'])]:
            with w.db.conn:w.db.conn.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('recent_colors',raw))
            w.close();app.processEvents();w=window()
            check('Startup color history '+str(len(checks)),[w.editor_tools.recent.itemText(i) for i in range(w.editor_tools.recent.count())]==colors)
            check('Raw optional value retained '+str(len(checks)),w.db.conn.execute('SELECT value FROM config WHERE key=?',('recent_colors',)).fetchone()[0]==raw)
        check('Unrelated setting preserved',w.db.get('quantity')==7)
        check('Customers/orders/jobs/profiles/migrations preserved during recovery',snapshot(w.db.conn)==before)
        check('Library rows and serials preserved during recovery',snapshot(w.tray.conn)==library_before)
        w.grab().save(str(out/'recovered-startup.png'))

        w.studio.open_job(first.id);w.set_color('background','#112233');stale=w._autosave_callback
        QTimer.singleShot(0,stale);choose(QMessageBox.Discard);w.home();wait(2500)
        check('Discard with queued callback and actual timeout preserves saved portrait',w.db.load_job(first.id).photos[0].background=='#ADD8E6')
        check('Discard restores active model and clears dirty state',w.photo.background=='#ADD8E6' and not w.dirty)
        check('Explicit Save after Discard cannot resurrect edits',w.save_job() and w.db.load_job(first.id).photos[0].background=='#ADD8E6')

        w.studio.open_job(first.id);w.set_color('background','#223344');choose(QMessageBox.Save);w.home()
        check('Save decision persists latest state',not w.dirty and w.db.load_job(first.id).photos[0].background=='#223344')
        w.studio.open_job(first.id);w.set_color('background','#334455');choose(QMessageBox.Cancel);w.home()
        check('Cancel keeps editor and edits',w.stack.currentIndex()==1 and w.dirty and w.photo.background=='#334455')
        wait(2800)
        check('Normal autosave resumes after Cancel/reopen',not w.dirty and w.db.load_job(first.id).photos[0].background=='#334455')

        w.set_color('background','#112233');stale=w._autosave_callback
        choose(QMessageBox.Discard);w.studio.open_job(second.id)
        w.set_color('background','#445566');QTimer.singleShot(0,stale);wait(100)
        check('Old callback cannot prematurely save next document',w.dirty and w.db.load_job(second.id).photos[0].background=='#ADD8E6')
        wait(2700)
        check('Next document autosaves normally',not w.dirty and w.db.load_job(second.id).photos[0].background=='#445566')
        check('Old document remains at last completed save',w.db.load_job(first.id).photos[0].background=='#334455')

        w.start_workflow('portrait');unsaved=w.job.id;w.photo.layers=[Layer(item.asset)]
        w.set_color('background','#112233');choose(QMessageBox.Discard);w.studio.show(w.studio.library);wait(2500)
        check('New unsaved Discard unloads without creating a job',w.photo is None and not w.db.conn.execute('SELECT 1 FROM jobs WHERE id=?',(unsaved,)).fetchone())
        w.studio.open_job(first.id);w.set_color('background','#112233');choose(QMessageBox.Discard);w.close()
        w=window();check('Close Discard and reopening preserve saved state',w.db.load_job(first.id).photos[0].background=='#334455')
        check('Library serials and rows unchanged after navigation',snapshot(w.tray.conn)==library_before)
        after=snapshot(w.db.conn)
        check('Only deliberately edited jobs changed',all(after[k]==v for k,v in before.items() if k!='jobs'))
        for label,conn in [('main',w.db.conn),('library',w.tray.conn)]:
            check(label+' SQLite integrity',conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
            check(label+' foreign-key integrity',conn.execute('PRAGMA foreign_key_check').fetchall()==[])
        check('Original image hash unchanged',hashlib.sha256(source.read_bytes()).hexdigest()==digest)
        check('No warning/error dialogs',not errors)
        result=dict(ok=True,checks=checks,elapsed_seconds=round(time.monotonic()-start,2),frozen=bool(getattr(__import__('sys'),'frozen',False)))
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return 0
    except Exception as error:
        (out/'result.json').write_text(json.dumps(dict(ok=False,checks=checks,error=str(error),errors=errors),indent=2),encoding='utf-8')
        raise
    finally:
        QMessageBox.warning=old_warning
        for w in windows:
            if w.isVisible():
                while w.busy:app.processEvents();time.sleep(.01)
                w.dirty=False;w.close()
