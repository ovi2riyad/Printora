"""Expanded isolated acceptance. Customer details here are synthetic fixtures only."""
import copy
from pathlib import Path
from app.services.orders import write_order_pdf,OrderStore
from app.services.print_sessions import PrintSessionStore
from app.services.layout import validate_layout,resize_copies
from app.services.profiles import normalize_profile


def verify_management(w,out,wait,portrait_items,joint_items):
    customer=w.studio.customers.save(dict(name='Synthetic acceptance customer',mobile='00000000001',notes='Generated isolated diagnostic fixture'))
    sources=len(w.tray.sources());count=len(w.tray.items)
    w.studio.import_customer_id=customer['id'];w.import_to_cropper(paths=[portrait_items[0].source]);wait(w)
    assert len(w.tray.sources())==sources and len(w.tray.items)==count
    assert portrait_items[0].id in w.studio.customers.photo_ids(customer['id'])
    compositions=[]
    for item in portrait_items[:3]:
        w.dirty=False;w.use_crops('portrait',[item]);wait(w)
        w.apply_composition('balanced',dict(top=3,bottom=3,left=2,right=2,horizontal=.5,vertical=.5,subject_scale=1));wait(w)
        w.save_job();compositions.append(copy.deepcopy(w.job))
    for items in ([joint_items[0]],portrait_items[:2]):
        w.dirty=False;w.use_crops('joint',items);wait(w);w.save_job();compositions.append(copy.deepcopy(w.job))
    assert len(compositions[-2].photos[0].layers)==1 and len(compositions[-1].photos[0].layers)==2
    w.editor_tools.group();w.commit_transform(0,w.photo.layers[0].x+.01,w.photo.layers[0].y,w.photo.layers[0].scale,w.photo.layers[0].rotation);wait(w)
    assert w.photo.layers[0].group==w.photo.layers[1].group
    w.commit_paint(0,dict(mode='erase',points=[[.01,.01]],radius=.01,hardness=.8,opacity=.5));wait(w)
    recipe=normalize_profile(dict(name='Synthetic joint recipe',kind='Joint',width=55,height=45,paper_orientation='landscape',margin=8,gap_x=.3,gap_y=.3))
    w.db.save_profile(recipe);w.refresh_profiles();w.profile_picker.setCurrentText(recipe['name']);w.apply_selected_profile();wait(w)
    assert w.job.print_settings['margin']==8 and w.photo.layers[0].mask_strokes[-1]['opacity']==.5
    compositions[-1]=copy.deepcopy(w.job)
    multi=w.studio.multi;w.dirty=False;w.studio.show(multi);multi.add_saved_jobs(compositions);wait(w)
    for i,n in enumerate((4,8,2,4,4)):multi.table.cellWidget(i,2).setValue(n);wait(w)
    assert len(multi.job.photos)==5 and sum(p.quantity for p in multi.job.photos)==22
    validate_layout(multi.job)
    last=max(multi.job.placements,key=lambda r:(r.page,r.y+r.height));last.x+=.01;validate_layout(multi.job);multi.placement_changed()
    session_id=multi.session_id;positions=[vars(r).copy() for r in multi.job.placements]
    multi.new();multi.load_session(session_id);wait(w);assert [vars(r) for r in multi.job.placements]==positions
    w.grab().save(str(out/'multi-photo-print.png'))
    order=w.studio.orders.create(multi.job,customer['id']);original=w.studio.orders.load_job(order['id']).to_dict()
    event,job=w.studio.orders.begin_export(order['id'],out/'v3-order.pdf')
    w.run(lambda:write_order_pdf(job,out/'v3-order.pdf',event,w.studio.orders.marker(event)),lambda result:w.studio.orders.finish_export(event,result));wait(w)
    assert w.studio.orders.get(order['id'])['status']=='Ready'
    w.studio.customers.save(dict(name='Synthetic revised customer',mobile='00000000002'),customer['id'])
    assert w.studio.orders.get(order['id'])['customer_mobile']=='00000000001'
    w.studio.customer_page.refresh();w.studio.customer_page.search.setText('00000000002');w.studio.show(w.studio.customer_page);w.grab().save(str(out/'customers.png'))
    w.studio.customer_orders(customer['id']);w.studio.order_page.current_id=order['id'];w.studio.order_page.refresh();w.grab().save(str(out/'orders.png'))
    reprint=w.studio.orders.duplicate(order['id']);changed=w.studio.orders.load_job(reprint['id']);changed.photos[0].quantity+=2;resize_copies(changed);w.studio.orders.update_draft(reprint['id'],changed)
    event,job=w.studio.orders.begin_export(reprint['id'],out/'v3-reprint.pdf')
    w.run(lambda:write_order_pdf(job,out/'v3-reprint.pdf',event,w.studio.orders.marker(event)),lambda result:w.studio.orders.finish_export(event,result));wait(w)
    # Layout generation was persisted at export, but compositions of the old order stay fixed.
    old=w.studio.orders.load_job(order['id']).to_dict()
    assert old['photos']==original['photos'] and old['print_settings']==original['print_settings']
    assert sum(p.quantity for p in w.studio.orders.load_job(reprint['id']).photos)==24
    w.dirty=False
    return dict(customer_id=customer['id'],order_id=order['id'],session_id=session_id),[
        'optional customer import with source deduplication','balanced physical framing controls',
        'group transforms and brush opacity persistence','full print recipe application',
        'five-composition mixed-size session with 22 copies','saved manual session placements',
        'immutable customer and composition order snapshots','mobile search and order history',
        '24-copy reprint without changing historical order']


def verify_restored_management(db,state,out):
    orders=OrderStore(db);sessions=PrintSessionStore(db)
    order=orders.get(state['order_id']);job=orders.load_job(order['id'])
    assert order['customer_mobile']=='00000000001'
    assert all(Path(layer.source).is_file() and (not layer.mask or Path(layer.mask).is_file()) for p in job.photos for layer in p.layers)
    assert sum(p.quantity for p in sessions.load(state['session_id']).photos)==22
    new=orders.duplicate(order['id']);event,job=orders.begin_export(new['id'],out/'v3-restored-reprint.pdf')
    # This diagnostic runs on the GUI thread; real UI exports dispatch the same writer to a worker.
    orders.finish_export(event,write_order_pdf(job,out/'v3-restored-reprint.pdf',event,orders.marker(event)))
    assert orders.get(new['id'])['status']=='Ready'
