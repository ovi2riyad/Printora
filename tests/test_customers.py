from PIL import Image
from app.core.database import Database
from app.services.customers import CustomerStore,normalized_mobile
from app.services.cropping import CropTray
from app.services.storage import backup_data,prepare_restore,install_restore


def test_customer_mobile_ids_duplicates_archive_and_links(tmp_path):
    root=tmp_path/'data';root.mkdir();db=Database(root/'studio.db');store=CustomerStore(db);tray=CropTray(root=root/'library')
    a=store.save(dict(name='Riyad',mobile='+880 ১৭১২-345678',alternative_mobile='01900 123456'))
    b=store.save(dict(name='Shared family',mobile='+8801712345678'));c=store.save(dict(name='No phone'))
    assert a['id']!=b['id'] and a['serial']!=b['serial']
    assert normalized_mobile('+880 ১৭১২-345678')=='8801712345678'
    assert len(store.search('01712345678'))==2 and store.search('01900123456')[0]['id']==a['id']
    assert len(store.duplicates('+8801712345678'))==2
    p=tray.add('Person',Image.new('RGB',(20,30)))
    store.assign_photos(a['id'],[p.id],tray);store.assign_photos(a['id'],[p.id],tray)
    assert store.photo_ids(a['id'])=={p.id}
    store.archive(a['id']);assert a['id'] not in {r['id'] for r in store.search()}
    assert store.search('Riyad',True)[0]['id']==a['id'];store.archive(a['id'],False)
    oldserial=a['serial'];a=store.save(dict(name='Changed',mobile=a['mobile']),a['id']);assert a['serial']==oldserial
    db.conn.close();tray.close();db=Database(root/'studio.db');assert CustomerStore(db).get(c['id'])['mobile']=='';db.conn.close()


def test_linked_job_update_and_migration_transaction_rollback(tmp_path):
    from app.models.domain import Job,Photo
    from app.core.migrations import migrate
    import sqlite3,pytest
    db=Database(tmp_path/'studio.db');store=CustomerStore(db);c=store.save(dict(name='Linked'));job=Job(photos=[Photo()]);db.save_job(job)
    with db.conn:db.conn.execute('INSERT INTO customer_job_links VALUES(?,?)',(c['id'],job.id))
    job.name='Edited job';db.save_job(job);assert db.load_job(job.id).name=='Edited job'
    with pytest.raises(sqlite3.OperationalError):migrate(db.conn,99,['CREATE TABLE must_rollback(id INTEGER)','INVALID SQL'])
    assert not db.conn.execute("SELECT 1 FROM sqlite_master WHERE name='must_rollback'").fetchone()
    assert not db.conn.execute('SELECT 1 FROM schema_migrations WHERE version=99').fetchone();db.conn.close()


def test_future_database_schema_is_refused_without_reset(tmp_path):
    import pytest
    db=Database(tmp_path/'studio.db');CustomerStore(db)
    with db.conn:db.conn.execute('INSERT INTO schema_migrations(version) VALUES(999)')
    db.conn.close()
    with pytest.raises(ValueError,match='newer'):Database(tmp_path/'studio.db')


def test_source_assignment_reconciles_after_crop_and_restore(tmp_path):
    root=tmp_path/'old';root.mkdir();db=Database(root/'studio.db');store=CustomerStore(db);tray=CropTray(root=root/'library')
    source=tmp_path/'source.png';Image.new('RGB',(20,30),'red').save(source);path=tray.import_source(source)
    c=store.save(dict(name='Synthetic Customer'));store.assign_sources(c['id'],[path],tray)
    p=tray.add('Crop',Image.new('RGB',(15,20)),path);store.reconcile(tray);store.reconcile(tray)
    assert store.photo_ids(c['id'])=={p.id}
    store.unlink_photos(c['id'],[p.id]);store.reconcile(tray);assert not store.photo_ids(c['id'])
    store.assign_photos(c['id'],[p.id],tray);assert store.photo_ids(c['id'])=={p.id}
    archive=tmp_path/'backup.zip';backup_data(root,archive);new=tmp_path/'new';stage=prepare_restore(archive,new);install_restore(stage,new)
    restored=Database(new/'studio.db');assert CustomerStore(restored).photo_ids(c['id'])=={p.id};assert restored.conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    restored.conn.close();db.conn.close();tray.close()
