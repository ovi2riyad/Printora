"""Editable multi-composition sessions reuse Job as their only document payload."""
import copy
import json
import uuid
from app.core.migrations import migrate
from app.services.customers import CustomerStore,rows
from app.services.layout import auto_layout,validate_layout
from app.models.domain import Job


def add_composition(job,photo,origin_job_id=''):
    p=copy.deepcopy(photo);p.provenance=dict(p.provenance,origin_photo_id=p.id,origin_job_id=origin_job_id);p.id=uuid.uuid4().hex;job.photos.append(p);return p


def choose_orientation(photos,settings,automatic=True):
    if not photos:raise ValueError('Add compositions before arranging the sheet.')
    candidates=[];errors=[]
    current=bool(settings.get('landscape'))
    for landscape in ((current,not current) if automatic else (current,)):
        candidate=dict(settings,landscape=landscape)
        try:
            placements=auto_layout(photos,candidate);pages=max(r.page for r in placements)+1
            probe=Job(photos=photos,placements=placements,page_count=pages,print_settings=candidate);validate_layout(probe)
            candidates.append((pages,landscape!=current,candidate,placements))
        except ValueError as e:errors.append(str(e))
    if not candidates:raise ValueError('Neither requested paper arrangement fits. '+ '; '.join(errors))
    pages,_,selected,placements=min(candidates,key=lambda x:x[:2])
    return selected,placements,pages


class PrintSessionStore:
    def __init__(self,db):
        self.db=db;self.conn=db.conn;CustomerStore(db)
        migrate(self.conn,3,["CREATE TABLE print_sessions(id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,customer_id TEXT REFERENCES customers(id) ON DELETE RESTRICT,name TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP,updated TEXT DEFAULT CURRENT_TIMESTAMP)",'CREATE INDEX sessions_updated ON print_sessions(updated)'])
    def save(self,job,session_id=None,customer_id=None):
        if not job.photos and not session_id:raise ValueError('Add compositions before saving a session.')
        for p in job.photos:p.validate()
        session_id=session_id or uuid.uuid4().hex
        with self.conn:
            self.conn.execute('INSERT INTO jobs(id,name,payload,updated) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET name=excluded.name,payload=excluded.payload,updated=excluded.updated',(job.id,job.name,json.dumps(job.to_dict())))
            self.conn.execute('INSERT INTO print_sessions(id,job_id,customer_id,name) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,updated=CURRENT_TIMESTAMP',(session_id,job.id,customer_id,job.name))
        return session_id
    def list(self):return rows(self.conn.execute('SELECT * FROM print_sessions ORDER BY updated DESC LIMIT 200'))
    def load(self,id):
        row=self.conn.execute('SELECT job_id FROM print_sessions WHERE id=?',(id,)).fetchone()
        if not row:raise ValueError('Print session no longer exists.')
        return self.db.load_job(row[0])
