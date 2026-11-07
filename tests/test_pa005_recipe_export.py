"""Recipe export safety checks use disposable sources and real Qt callbacks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import hashlib
import json
from pathlib import Path
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox,QPushButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.core.database import Database
from app.models.domain import Job,Photo,Layer
from app.ui.profiles import Profiles


@pytest.fixture
def exporter(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    root=tmp_path/'data';root.mkdir();db=Database(root/'studio.db')
    widget=Profiles(db,lambda:None);widget.show();app.processEvents();warnings=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:warnings.append(str(a[-1])))
    yield widget,db,warnings
    widget.close();app.processEvents();db.conn.close()


def click_export(widget,monkeypatch,target):
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(target),'JSON (*.json)'))
    button=next(b for b in widget.findChildren(QPushButton) if b.text()=='Export JSON')
    QTest.mouseClick(button,Qt.LeftButton)


def test_recipe_export_rejects_original_photo(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter
    source=tmp_path/'original.png';Image.new('RGB',(30,40),'orange').save(source)
    before=source.read_bytes();digest=hashlib.sha256(before).hexdigest()
    db.save_job(Job(photos=[Photo(layers=[Layer(str(source))])]))
    click_export(widget,monkeypatch,source)
    assert source.read_bytes()==before
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    assert warnings


@pytest.mark.parametrize('suffix',['.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff','.pdf','.zip','.txt',''])
def test_non_json_names_are_rejected_without_renaming(exporter,tmp_path,monkeypatch,suffix):
    widget,db,warnings=exporter;target=tmp_path/('profiles'+suffix)
    target.write_bytes(b'preserve existing user-file bytes');before=target.read_bytes()
    listing=set(tmp_path.iterdir());click_export(widget,monkeypatch,target)
    assert target.read_bytes()==before and set(tmp_path.iterdir())==listing
    assert warnings


def test_untracked_photo_disguised_as_profiles_json_is_preserved(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;target=tmp_path/'profiles.json'
    Image.new('RGB',(30,40),'red').save(target,format='PNG');before=target.read_bytes()
    click_export(widget,monkeypatch,target)
    assert target.read_bytes()==before and warnings


@pytest.mark.parametrize('relative',['profiles.json','library/sources/original.json','library/photos/prepared.json','cache/mask.json','job_assets/crop.json','models/file.json'])
def test_application_data_destinations_are_protected(exporter,monkeypatch,relative):
    widget,db,warnings=exporter;target=db.path.parent/relative;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('{"preserve":true}');before=target.read_bytes()
    click_export(widget,monkeypatch,target)
    assert target.read_bytes()==before and warnings


@pytest.mark.parametrize('field',['source','mask'])
def test_known_asset_paths_are_protected_even_with_json_contents(exporter,tmp_path,monkeypatch,field):
    widget,db,warnings=exporter;source=tmp_path/'source.json';mask=tmp_path/'mask.json'
    for p in (source,mask):p.write_text('{"retained original reference":true}')
    db.save_job(Job(photos=[Photo(layers=[Layer(str(source),mask=str(mask))])]))
    target=source if field=='source' else mask;before=target.read_bytes()
    click_export(widget,monkeypatch,target)
    assert target.read_bytes()==before and warnings


def test_path_alias_and_case_cannot_bypass_known_original_guard(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;target=tmp_path/'original.json';target.write_text('{"retain":true}')
    db.save_job(Job(photos=[Photo(layers=[Layer(str(target))])]))
    folder=tmp_path/'folder';folder.mkdir();before=target.read_bytes()
    click_export(widget,monkeypatch,folder/'..'/target.name.upper())
    assert target.read_bytes()==before and warnings


def test_hard_link_alias_is_protected(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;source=tmp_path/'original.json';source.write_text('{"original":true}')
    alias=tmp_path/'recipes.json';os.link(source,alias)
    db.save_job(Job(photos=[Photo(layers=[Layer(str(source))])]))
    before=source.read_bytes();click_export(widget,monkeypatch,alias)
    assert alias.read_bytes()==source.read_bytes()==before and warnings


def test_historical_order_only_original_is_protected(exporter,tmp_path,monkeypatch):
    from app.services.orders import OrderStore
    widget,db,warnings=exporter;target=tmp_path/'historical-only.json';target.write_text('{"original":true}')
    store=OrderStore(db);order=store.create(Job(photos=[Photo(layers=[Layer(str(target))])]))
    assert not db.jobs();before=target.read_bytes();order_before=store.load_job(order['id']).to_dict()
    click_export(widget,monkeypatch,target)
    assert target.read_bytes()==before and warnings
    assert store.load_job(order['id']).to_dict()==order_before


def test_successful_historical_artifact_is_protected(exporter,tmp_path,monkeypatch):
    from app.services.orders import OrderStore
    widget,db,warnings=exporter;source=tmp_path/'source.png';Image.new('RGB',(20,30)).save(source)
    store=OrderStore(db);order=store.create(Job(photos=[Photo(layers=[Layer(str(source))])]))
    target=tmp_path/'historical.json';target.write_text('{"historical":true}');before=target.read_bytes()
    with db.conn:db.conn.execute('INSERT INTO print_events(id,order_id,path,status) VALUES(?,?,?,?)',('synthetic-event',order['id'],str(target),'Ready'))
    click_export(widget,monkeypatch,target)
    assert target.read_bytes()==before and warnings


@pytest.mark.parametrize('existing',[False,True])
def test_valid_recipe_export_and_explicit_json_replacement(exporter,tmp_path,monkeypatch,existing):
    widget,db,warnings=exporter;target=tmp_path/'profiles.json'
    if existing:target.write_text('{"previous export":true}')
    before=db.profiles();click_export(widget,monkeypatch,target)
    assert json.loads(target.read_text())==before and not warnings
    assert db.profiles()==before and not list(tmp_path.glob('.printora-recipes-*.tmp'))


def test_uppercase_json_extension_is_not_renamed(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;target=tmp_path/'chosen.JSON'
    click_export(widget,monkeypatch,target)
    assert json.loads(target.read_text())==db.profiles() and not warnings
    assert not (tmp_path/'chosen.json.json').exists()


@pytest.mark.parametrize('failure',['serialize','fsync','replace'])
def test_atomic_failure_keeps_existing_json_unchanged(exporter,tmp_path,monkeypatch,failure):
    import app.services.recipe_export as module
    widget,db,warnings=exporter;target=tmp_path/'profiles.json';target.write_text('{"old":true}')
    before=target.read_bytes()
    def fail(*a,**k):raise OSError('Synthetic unavailable/read-only output')
    with monkeypatch.context() as patch:
        if failure=='serialize':patch.setattr(module.json,'dumps',fail)
        else:patch.setattr(module.os,failure,fail)
        click_export(widget,patch,target)
    assert target.read_bytes()==before and warnings
    assert not list(tmp_path.glob('.printora-recipes-*.tmp'))


def test_image_appearing_during_export_is_not_replaced(exporter,tmp_path,monkeypatch):
    import app.services.recipe_export as module
    widget,db,warnings=exporter;target=tmp_path/'profiles.json';original_fsync=module.os.fsync;image_bytes=[]
    def race(fd):
        Image.new('RGB',(20,30),'orange').save(target,format='PNG');image_bytes.append(target.read_bytes());original_fsync(fd)
    monkeypatch.setattr(module.os,'fsync',race)
    click_export(widget,monkeypatch,target)
    assert target.read_bytes()==image_bytes[0] and warnings
    assert not list(tmp_path.glob('.printora-recipes-*.tmp'))


def test_cancel_and_unavailable_destination_do_not_write(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;before=set(tmp_path.rglob('*'))
    click_export(widget,monkeypatch,'');assert set(tmp_path.rglob('*'))==before and not warnings
    click_export(widget,monkeypatch,tmp_path/'unavailable'/'profiles.json')
    assert not (tmp_path/'unavailable').exists() and warnings


def test_malformed_saved_references_fail_closed_without_mutation(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;job=Job(photos=[Photo()]);db.save_job(job)
    with db.conn:db.conn.execute('UPDATE jobs SET payload=? WHERE id=?',('{broken-json',job.id))
    target=tmp_path/'profiles.json';target.write_text('{"retain":true}');before=target.read_bytes()
    click_export(widget,monkeypatch,target)
    assert target.read_bytes()==before and warnings
    assert db.conn.execute('SELECT payload FROM jobs WHERE id=?',(job.id,)).fetchone()[0]=='{broken-json'


def test_malformed_optional_color_history_does_not_block_recipe_export(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter
    with db.conn:db.conn.execute('INSERT INTO config VALUES(?,?)',('recent_colors','{broken-json'))
    target=tmp_path/'profiles.json';click_export(widget,monkeypatch,target)
    assert json.loads(target.read_text())==db.profiles() and not warnings
    assert db.conn.execute('SELECT value FROM config WHERE key=?',('recent_colors',)).fetchone()[0]=='{broken-json'


def test_same_filename_in_another_destination_preserves_original(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;source_dir=tmp_path/'originals';destination=tmp_path/'exports'
    source_dir.mkdir();destination.mkdir();source=source_dir/'profiles.json'
    Image.new('RGB',(30,40),'orange').save(source,format='PNG');before=source.read_bytes()
    db.save_job(Job(photos=[Photo(layers=[Layer(str(source))])]))
    target=destination/source.name;click_export(widget,monkeypatch,target)
    assert source.read_bytes()==before and not warnings
    assert json.loads(target.read_text())==db.profiles()


def test_windows_alternate_stream_destination_is_rejected(exporter,tmp_path,monkeypatch):
    widget,db,warnings=exporter;source=tmp_path/'original.png';Image.new('RGB',(20,30)).save(source)
    before=source.read_bytes();target=Path(str(source)+':recipes.json')
    click_export(widget,monkeypatch,target)
    assert source.read_bytes()==before and warnings
    assert not target.exists()


def test_export_preserves_original_hashes_library_serials_and_business_records(exporter,tmp_path,monkeypatch):
    from app.services.cropping import CropTray
    from app.services.customers import CustomerStore
    from app.services.orders import OrderStore
    widget,db,warnings=exporter;tray=CropTray(root=db.path.parent/'library')
    source=tmp_path/'external-original.png';Image.new('RGB',(30,40),'orange').save(source)
    managed=tray.import_source(source);item=tray.add('Synthetic photo',Image.open(source),managed)
    customers=CustomerStore(db);customer=customers.save(dict(name='Synthetic fixture',mobile='01700000000'))
    customers.assign_photos(customer['id'],[item.id],tray)
    job=Job(photos=[Photo(layers=[Layer(item.asset)])]);db.save_job(job);OrderStore(db).create(job,customer['id'])
    def snapshot(conn):
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in tables}
    before_main=snapshot(db.conn);before_library=snapshot(tray.conn)
    originals=[source,Path(managed),Path(item.asset),Path(item.thumb)]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    try:
        target=tmp_path/'profiles.json';click_export(widget,monkeypatch,target)
        assert json.loads(target.read_text())==db.profiles() and not warnings
        assert snapshot(db.conn)==before_main and snapshot(tray.conn)==before_library
        assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
        for conn in (db.conn,tray.conn):
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally:tray.close()
