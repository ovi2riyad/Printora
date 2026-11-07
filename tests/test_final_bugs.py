"""Reproduce the remaining audit findings with disposable data."""
import json,os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from app.core.database import Database
from app.services.cropping import CropTray
from app.services.storage import backup_data
from app.models.domain import Photo,Layer,Job

@pytest.fixture
def app():return QApplication.instance() or QApplication([])

def test_pa007_missing_unused_original_blocks_backup(tmp_path):
    root=tmp_path/'data';root.mkdir();db=Database(root/'studio.db');tray=CropTray(root=root/'library')
    item=tray.add('unused',Image.new('RGB',(30,40)));Path(item.asset).unlink()
    target=tmp_path/'backup.zip'
    with pytest.raises(ValueError,match='missing|Missing'):backup_data(root,target)
    assert not target.exists();tray.close();db.conn.close()

def test_pa006_extension_repair_preserves_photo_source_and_serial(tmp_path):
    original=tmp_path/'scan.jpg';Image.new('RGB',(30,40)).save(original)
    tray=CropTray(root=tmp_path/'library');old=tray.import_source(original)
    item=tray.add('portrait',Image.new('RGB',(20,30)),old);id,serial=item.id,item.serial
    Path(old).unlink();replacement=tmp_path/'scan.jpeg';replacement.write_bytes(original.read_bytes())
    new=tray.import_source(replacement)
    assert item.source==new
    assert tray.conn.execute('SELECT source FROM photos WHERE id=?',(id,)).fetchone()[0]==new
    tray.close();tray=CropTray(root=tmp_path/'library');assert tray.items[0].serial==serial and tray.items[0].source==new;tray.close()

def test_pa009_processed_dimensions_not_original(tmp_path):
    from app.services.imaging import resolution_warnings
    original=tmp_path/'large.png';mask=tmp_path/'mask.png'
    Image.new('RGB',(4000,5000)).save(original);Image.new('RGBA',(1600,2000)).save(mask)
    photo=Photo(width=180,height=225,layers=[Layer(str(original),str(mask))])
    assert resolution_warnings(photo)

def test_pa004_collision_rejects_entire_import(app,tmp_path,monkeypatch):
    from app.ui.profiles import Profiles
    db=Database(tmp_path/'studio.db');before=db.profiles();recipe=dict(before[0],recipe_id='22222222-2222-4222-8222-222222222222')
    path=tmp_path/'recipes.json';path.write_text(json.dumps([recipe]))
    errors=[];monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(str(path),''));monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a[-1]))
    widget=Profiles(db,lambda:None);widget.import_json()
    assert db.profiles()==before and errors;widget.close();db.conn.close()

def test_pa013_alternate_shared_number_warns(app,tmp_path,monkeypatch):
    from app.services.customers import CustomerStore
    from app.ui.customers import CustomerDialog
    db=Database(tmp_path/'studio.db');store=CustomerStore(db);store.save(dict(name='First',mobile='01712345678'))
    calls=[];monkeypatch.setattr(QMessageBox,'question',lambda *a:calls.append(a) or QMessageBox.No)
    dialog=CustomerDialog(store);dialog.fields['name'].setText('Second');dialog.fields['alternative_mobile'].setText('01712345678');dialog.accept()
    assert calls and dialog.result_customer is None;dialog.close();db.conn.close()

@pytest.fixture
def window(app,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    from app.ui.studio_window import StudioWindow
    w=StudioWindow();yield w
    w.hardware.shutdown();w.dirty=False;w.timer.stop();w.invalidate_autosave();w.pool.waitForDone();w.close()

def test_pa010_bad_dashboard_job_recovers(window,monkeypatch):
    w=window;w.db.conn.execute('INSERT INTO jobs(id,name,payload) VALUES(?,?,?)',('bad','Damaged job','{"photos":42}'));w.db.conn.commit()
    errors=[];monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a[-1]))
    w.studio.open_job('bad')
    assert errors and w.db.conn.execute('SELECT payload FROM jobs WHERE id="bad"').fetchone()[0]=='{"photos":42}'

def test_pa011_import_summary_is_persistent(window,tmp_path):
    w=window;good=tmp_path/'valid.png';bad=tmp_path/'corrupt.png';Image.new('RGB',(20,30)).save(good);bad.write_bytes(b'corrupt')
    def run(fn,done,*a):done(fn())
    w.cropper.run=run;w.cropper.import_sources(paths=[str(good),str(bad)])
    assert hasattr(w.cropper,'import_summary') and '1 failed' in w.cropper.import_summary.text()

def test_pa012_customer_scope_intersects_text(window):
    w=window;customer=w.studio.customers.save(dict(name='Customer'))
    a=w.tray.add('Alpha',Image.new('RGB',(20,30)));b=w.tray.add('Beta',Image.new('RGB',(20,30)))
    w.studio.customers.assign_photos(customer['id'],[a.id,b.id],w.tray)
    page=w.studio.library;page.customer_id=customer['id'];page.gallery.search.setText('Alpha');page.gallery.refresh()
    assert set(page.gallery.rows)=={a.id}

def test_pa008_tools_can_scroll_without_overlapping(window,app):
    w=window;w.resize(1050,740);w.show();w.studio.show(w.studio.tools);app.processEvents()
    from PySide6.QtWidgets import QScrollArea
    assert w.studio.tools.tabs.findChildren(QScrollArea)
