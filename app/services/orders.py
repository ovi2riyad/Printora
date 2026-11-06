"""Immutable order composition snapshots and recoverable PDF export attempts."""
import copy
import hashlib
import json
import os
import uuid
from pathlib import Path
from app.core.migrations import migrate
from app.models.domain import Job,Photo,Placement
from app.services.customers import CustomerStore,rows,normalized_mobile
from app.services.layout import auto_layout,validate_layout
from app.services.pdf import export_pdf


STATUSES=('Draft','Processing','Ready','Completed','Cancelled')


class OrderStore:
    def __init__(self,db):
        self.db=db;self.conn=db.conn;self.customers=CustomerStore(db)
        migrate(self.conn,2,[
            "CREATE TABLE orders(serial INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,customer_id TEXT REFERENCES customers(id) ON DELETE RESTRICT,customer_name TEXT NOT NULL DEFAULT '',customer_mobile TEXT NOT NULL DEFAULT '',mobile_search TEXT NOT NULL DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP,status TEXT NOT NULL DEFAULT 'Draft',notes TEXT NOT NULL DEFAULT '',payload TEXT NOT NULL,parent_id TEXT REFERENCES orders(id) ON DELETE RESTRICT)",
            'CREATE TABLE order_items(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,position INTEGER NOT NULL,snapshot TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),UNIQUE(order_id,position))',
            "CREATE TABLE print_events(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,created TEXT DEFAULT CURRENT_TIMESTAMP,finished TEXT,path TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Processing',sha256 TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '')",
            'CREATE INDEX orders_customer ON orders(customer_id,created)',
            'CREATE INDEX orders_phone ON orders(mobile_search)',
            'CREATE INDEX orders_status_date ON orders(status,created)',
            'CREATE INDEX order_items_order ON order_items(order_id)',
            'CREATE INDEX events_order ON print_events(order_id,created)'
        ])
        self.recover_exports()

    def get(self,id):
        found=rows(self.conn.execute('SELECT * FROM orders WHERE id=?',(id,)))
        if not found:raise ValueError('Order no longer exists.')
        return found[0]

    def search(self,text='',customer_id=None,status='',days=None):
        key=normalized_mobile(text);sql="SELECT * FROM orders WHERE (instr(lower(name||' '||customer_name||' '||printf('O%06d',serial)),lower(?))>0 OR (?<>'' AND instr(mobile_search,?)>0))";args=[text,key,key]
        if customer_id:sql+=' AND customer_id=?';args.append(customer_id)
        if status:sql+=' AND status=?';args.append(status)
        if days:sql+=" AND created>=datetime('now',?)";args.append(f'-{int(days)} days')
        return rows(self.conn.execute(sql+' ORDER BY serial DESC LIMIT 200',args))

    def create(self,job,customer_id=None,notes='',parent_id=None):
        if not job.photos or any(not p.layers for p in job.photos):raise ValueError('Add finished compositions before creating an order.')
        snapshot=copy.deepcopy(job);snapshot.id=uuid.uuid4().hex
        mapping={p.id:uuid.uuid4().hex for p in snapshot.photos}
        for p in snapshot.photos:p.provenance=dict(p.provenance,origin_photo_id=p.id,origin_job_id=job.id);p.id=mapping[p.id]
        for placement in snapshot.placements:placement.photo_id=mapping[placement.photo_id]
        customer=self.customers.get(customer_id) if customer_id else None
        if customer_id and not customer:raise ValueError('Customer no longer exists.')
        id=uuid.uuid4().hex;payload=snapshot.to_dict();payload.pop('photos')
        with self.conn:
            self.conn.execute('INSERT INTO orders(id,name,customer_id,customer_name,customer_mobile,mobile_search,notes,payload,parent_id) VALUES(?,?,?,?,?,?,?,?,?)',(id,job.name,customer_id,customer['name'] if customer else '',customer['mobile'] if customer else '',normalized_mobile(customer['mobile']) if customer else '',notes,json.dumps(payload),parent_id))
            self._save_items(id,snapshot.photos)
            if customer_id:self.conn.execute('UPDATE customers SET activity=CURRENT_TIMESTAMP WHERE id=?',(customer_id,))
        return self.get(id)

    def _save_items(self,id,photos):
        self.conn.execute('DELETE FROM order_items WHERE order_id=?',(id,))
        for i,p in enumerate(photos):
            data=copy.deepcopy(p.__dict__)
            from dataclasses import asdict
            data=asdict(p);data.pop('quantity')
            self.conn.execute('INSERT INTO order_items VALUES(?,?,?,?,?)',(uuid.uuid4().hex,id,i,json.dumps(data),p.quantity))

    def load_job(self,id):
        order=self.get(id);data=json.loads(order['payload']);data['photos']=[]
        for raw,qty in self.conn.execute('SELECT snapshot,quantity FROM order_items WHERE order_id=? ORDER BY position',(id,)):
            p=json.loads(raw);p['quantity']=qty;data['photos'].append(p)
        return Job.from_dict(data)

    def update_draft(self,id,job):
        if self.get(id)['status']!='Draft':raise ValueError('Duplicate or reprint this historical order before editing it.')
        for p in job.photos:p.validate()
        payload=job.to_dict();payload.pop('photos')
        with self.conn:self.conn.execute('UPDATE orders SET payload=? WHERE id=?',(json.dumps(payload),id));self._save_items(id,job.photos)

    def duplicate(self,id):
        old=self.get(id)
        return self.create(self.load_job(id),old['customer_id'],old['notes'],parent_id=id)

    def set_status(self,id,status):
        old=self.get(id)['status'];allowed={'Draft':('Cancelled',),'Ready':('Completed','Cancelled'),'Completed':(),'Cancelled':(),'Processing':()}
        if status not in allowed[old]:raise ValueError('This status change is not available. Create a reprint for completed/cancelled work.')
        with self.conn:self.conn.execute('UPDATE orders SET status=? WHERE id=?',(status,id))

    def begin_export(self,id,path):
        order=self.get(id)
        if order['status']!='Draft':raise ValueError('Reprint/duplicate the order to generate a new PDF.')
        target=str(Path(path).resolve())
        from app.services.export_safety import check_export_target
        check_export_target(target,self.db.path.parent,self.conn)
        if Path(target).suffix.lower()!='.pdf' or Path(target).is_relative_to(self.db.path.parent.resolve()):raise ValueError('Save the PDF outside application data using a .pdf filename.')
        if self.conn.execute("SELECT 1 FROM print_events WHERE path=? AND status='Ready'",(target,)).fetchone():raise ValueError('Choose a new filename to preserve the previous order PDF.')
        job=self.load_job(id)
        if not job.placements:
            if job.print_settings.get('auto_orientation'):
                from app.services.print_sessions import choose_orientation
                job.print_settings,job.placements,job.page_count=choose_orientation(job.photos,job.print_settings)
            else:job.placements=auto_layout(job.photos,job.print_settings);job.page_count=max(p.page for p in job.placements)+1
        validate_layout(job);self.update_draft(id,job)
        event=uuid.uuid4().hex
        with self.conn:
            self.conn.execute('INSERT INTO print_events(id,order_id,path) VALUES(?,?,?)',(event,id,target))
            self.conn.execute("UPDATE orders SET status='Processing' WHERE id=?",(id,))
        return event,job

    def marker(self,event):return self.db.path.parent/'export-recovery'/(event+'.json')
    def finish_export(self,event,result=None,error=''):
        row=self.conn.execute('SELECT order_id,status FROM print_events WHERE id=?',(event,)).fetchone()
        if not row:raise ValueError('Export attempt is missing.')
        if row[1]!='Processing':return
        if result:
            if not Path(result['path']).is_file() or file_hash(result['path'])!=result['sha256']:raise ValueError('Exported PDF no longer matches its recorded checksum.')
        with self.conn:
            self.conn.execute('UPDATE print_events SET status=?,sha256=?,error=?,finished=CURRENT_TIMESTAMP WHERE id=?',('Ready' if result else 'Failed',result['sha256'] if result else '',error,event))
            self.conn.execute('UPDATE orders SET status=? WHERE id=?',('Ready' if result else 'Draft',row[0]))
        self.marker(event).unlink(missing_ok=True)
    def events(self,id):return rows(self.conn.execute('SELECT * FROM print_events WHERE order_id=? ORDER BY created,id',(id,)))
    def recover_exports(self):
        for event, in self.conn.execute("SELECT id FROM print_events WHERE status='Processing'").fetchall():
            marker=self.marker(event)
            try:
                result=json.loads(marker.read_text(encoding='utf-8'))
                if result.get('event')!=event:raise ValueError('Unexpected event marker.')
                self.finish_export(event,result)
            except (OSError,ValueError,KeyError):self.finish_export(event,error='Interrupted export. Review the destination and try again using a new filename.')


def file_hash(path):
    with open(path,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write_order_pdf(job,path,event,marker):
    path=export_pdf(job,path,dpi=int(job.print_settings.get('dpi',300)))
    result=dict(event=event,path=str(Path(path).resolve()),sha256=file_hash(path))
    marker=Path(marker);marker.parent.mkdir(exist_ok=True)
    temporary=marker.with_suffix('.tmp');temporary.write_text(json.dumps(result),encoding='utf-8');os.replace(temporary,marker)
    return result
