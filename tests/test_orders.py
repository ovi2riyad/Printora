import json
from pathlib import Path
import pytest
from PIL import Image
from app.core.database import Database
from app.models.domain import Photo,Layer,Job
from app.services.customers import CustomerStore
from app.services.orders import OrderStore,write_order_pdf
from app.services.storage import referenced_assets,backup_data,prepare_restore,install_restore,clear_safe_cache


def setup_order(tmp_path):
    root=tmp_path/'data';root.mkdir();db=Database(root/'studio.db');customers=CustomerStore(db);orders=OrderStore(db)
    source=root/'original.png';Image.new('RGB',(200,250),'red').save(source)
    customer=customers.save(dict(name='Synthetic customer',mobile='01712 345678'))
    job=Job(name='Portrait test',photos=[Photo(layers=[Layer(str(source))])]);order=orders.create(job,customer['id'])
    return root,db,customers,orders,job,order,customer


def test_order_snapshot_reprint_search_and_pdf(tmp_path):
    root,db,customers,orders,job,order,customer=setup_order(tmp_path)
    customers.save(dict(name='Changed',mobile='01999'),customer['id']);job.photos[0].background='#00ff00'
    assert orders.get(order['id'])['customer_name']=='Synthetic customer'
    assert orders.load_job(order['id']).photos[0].background=='#ADD8E6'
    assert orders.search('01712345678')[0]['id']==order['id']
    event,snapshot=orders.begin_export(order['id'],tmp_path/'first.pdf')
    result=write_order_pdf(snapshot,tmp_path/'first.pdf',event,orders.marker(event));orders.finish_export(event,result)
    assert orders.get(order['id'])['status']=='Ready'
    with pytest.raises(ValueError):orders.update_draft(order['id'],snapshot)
    orders.set_status(order['id'],'Completed');new=orders.duplicate(order['id']);copy=orders.load_job(new['id']);copy.photos[0].quantity=8;copy.placements=[];orders.update_draft(new['id'],copy)
    assert orders.load_job(order['id']).photos[0].quantity==4 and orders.load_job(new['id']).photos[0].quantity==8
    assert new['parent_id']==order['id'] and new['serial']!=order['serial']
    assert Path(job.photos[0].layers[0].source).resolve() in referenced_assets(root)
    with pytest.raises(ValueError):orders.begin_export(new['id'],tmp_path/'first.pdf')
    db.conn.close()


def test_order_export_recovery_and_backup_remaps_history(tmp_path):
    root,db,customers,orders,job,order,customer=setup_order(tmp_path)
    event,snapshot=orders.begin_export(order['id'],tmp_path/'historical.pdf')
    write_order_pdf(snapshot,tmp_path/'historical.pdf',event,orders.marker(event))
    # Simulate a crash after atomic PDF+marker creation but before GUI history commit.
    orders=OrderStore(db);assert orders.get(order['id'])['status']=='Ready'
    archive=tmp_path/'backup.zip';backup_data(root,archive);newroot=tmp_path/'restored';install_restore(prepare_restore(archive,newroot),newroot)
    restored=Database(newroot/'studio.db');store=OrderStore(restored);layer=store.load_job(order['id']).photos[0].layers[0]
    assert Path(layer.source).is_relative_to(newroot) and Path(layer.source).is_file()
    assert Path(store.events(order['id'])[0]['path']).is_relative_to(newroot)
    assert Path(store.events(order['id'])[0]['path']).is_file()
    reprint=store.duplicate(order['id']);event,snapshot=store.begin_export(reprint['id'],tmp_path/'reprint.pdf');store.finish_export(event,error='Synthetic failure')
    assert store.get(reprint['id'])['status']=='Draft' and store.events(reprint['id'])[0]['status']=='Failed'
    restored.conn.close();db.conn.close()


def test_cache_protects_assets_referenced_only_by_historical_order(tmp_path):
    import os,time
    root,db,customers,orders,job,order,customer=setup_order(tmp_path)
    cache=root/'cache';cache.mkdir();path=cache/'historical-only.png';Image.new('RGB',(20,25)).save(path);os.utime(path,(time.time()-172800,)*2)
    standalone=Job(photos=[Photo(layers=[Layer(str(path))])]);orders.create(standalone)
    assert clear_safe_cache(root)['files']==0 and path.exists();db.conn.close()
