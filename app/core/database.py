import json
import os
import sqlite3
from pathlib import Path
from app.models.domain import Job
from app.services.profiles import normalize_profile

def data_root():
    p = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'StudioPhotoMaker'
    from app.services.storage import recover_restore
    recover_restore(p)
    p.mkdir(parents=True, exist_ok=True)
    return p

def starter_profiles():
    rows = [('Studio Portrait',45,55,''),('Studio Standard Photo',35,45,''),('Studio Joint Photo',55,45,''),('USA Passport',51,51,'USA'),('UK Passport',35,45,'UK'),('India Common Paper Photo',35,45,'India'),('India Consular Photo',51,51,'India'),('Malaysia ESD Visa',35,50,'Malaysia')]
    sources = {'USA':'https://travel.state.gov/content/travel/en/passports/how-apply/photos.html','UK':'https://www.gov.uk/photos-for-passports/photo-requirements','India':'https://www.passportindia.gov.in/','Malaysia':'https://esd.imi.gov.my/portal/'}
    rows.append(('Bangladesh Studio Portrait',45,55,'Bangladesh'))
    return [normalize_profile(dict(name=n,width=w,height=h,country=c,document_type=n,background='#ADD8E6' if not c else '#FFFFFF',border=True,border_color='#808080',border_mm=0.2,notes='Editable studio print-size starting point. Check current authority rules; digital modification may be prohibited. Joint profiles are studio compositions, not document presets.',url=sources.get(c,''),verification='Requires verification' if c else 'Studio preset')) for n,w,h,c in rows]

class Database:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_root() / 'studio.db'
        self.conn = sqlite3.connect(self.path)
        if self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
            if (self.conn.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] or 0)>4:
                self.conn.close();raise ValueError('This data was created by a newer Studio Photo Maker. Open it with the matching newer version.')
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,name TEXT,payload TEXT,updated TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS profiles(name TEXT PRIMARY KEY,payload TEXT); CREATE TABLE IF NOT EXISTS exports(path TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);')
        if not self.get('profiles_initialized', False):
            self.restore_profiles()
            self.set('profiles_initialized', True)
        # Additive migration only. Existing profile names/payloads and jobs stay intact.
        if self.get('profile_schema_version', 0) < 2:
            existing = {p['name'] for p in self.profiles()}
            for p in starter_profiles():
                if p['name'] not in existing:self.save_profile(p)
            self.set('profile_schema_version', 2)

    def get(self, key, default=None):
        row = self.conn.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self,key,value):
        with self.conn: self.conn.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(key,json.dumps(value)))

    def save_job(self,job):
        with self.conn: self.conn.execute('INSERT INTO jobs(id,name,payload,updated) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET name=excluded.name,payload=excluded.payload,updated=excluded.updated',(job.id,job.name,json.dumps(job.to_dict())))

    def load_job(self,id):
        row=self.conn.execute('SELECT payload FROM jobs WHERE id=?',(id,)).fetchone()
        if not row: raise ValueError('Job no longer exists.')
        return Job.from_dict(json.loads(row[0]))

    def jobs(self):
        return self.conn.execute('SELECT id,name,updated FROM jobs ORDER BY updated DESC').fetchall()

    def profiles(self):
        return [json.loads(r[0]) for r in self.conn.execute('SELECT payload FROM profiles ORDER BY name')]

    def save_profile(self,p):
        p=normalize_profile(p)
        with self.conn: self.conn.execute('INSERT OR REPLACE INTO profiles VALUES(?,?)',(p['name'],json.dumps(p)))

    def restore_profiles(self):
        """Restore missing starters without replacing customized profiles."""
        existing={p['name'] for p in self.profiles()}
        for p in starter_profiles():
            if p['name'] not in existing:self.save_profile(p)

    def rename_profile(self,old_name,p):
        p=normalize_profile(p)
        existing=next((raw for raw in self.profiles() if raw['name']==old_name),None)
        if existing:p['recipe_id']=normalize_profile(existing,validate=False)['recipe_id']
        if old_name != p['name'] and any(x['name']==p['name'] for x in self.profiles()):
            raise ValueError('A profile with this name already exists.')
        with self.conn:
            self.conn.execute('INSERT OR REPLACE INTO profiles VALUES(?,?)',(p['name'],json.dumps(p)))
            if old_name != p['name']:
                self.conn.execute('DELETE FROM profiles WHERE name=?',(old_name,))
                for key in ('default_profile','joint_profile'):
                    if self.get(key)==old_name:self.conn.execute('UPDATE config SET value=? WHERE key=?',(json.dumps(p['name']),key))

    def delete_profile(self,name):
        with self.conn:
            self.conn.execute('DELETE FROM profiles WHERE name=?',(name,))
            for key in ('default_profile','joint_profile'):
                if self.get(key)==name:self.conn.execute('DELETE FROM config WHERE key=?',(key,))
