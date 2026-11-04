import json
import os
import sqlite3
from pathlib import Path
from app.models.domain import Job

def data_root():
    p = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'StudioPhotoMaker'
    p.mkdir(parents=True, exist_ok=True)
    return p

def starter_profiles():
    rows = [('Studio Portrait',45,55,''),('Studio Standard Photo',35,45,''),('Studio Joint Photo',55,45,''),('USA Passport',51,51,'USA'),('UK Passport',35,45,'UK'),('India Common Paper Photo',35,45,'India'),('India Consular Photo',51,51,'India'),('Malaysia ESD Visa',35,50,'Malaysia')]
    sources = {'USA':'https://travel.state.gov/content/travel/en/passports/how-apply/photos.html','UK':'https://www.gov.uk/photos-for-passports/photo-requirements','India':'https://www.passportindia.gov.in/','Malaysia':'https://esd.imi.gov.my/portal/'}
    return [dict(name=n,width=w,height=h,country=c,document_type=n,orientation='Landscape' if w>h else 'Portrait',background='#ADD8E6' if not c else '#FFFFFF',border=True,border_color='#808080',border_mm=0.2,notes=('Print-size starting point. Verify current application rules. Digital editing may be prohibited. ' + ('India requirements vary by application or mission.' if c=='India' else 'ESD visa only; not a universal Malaysian passport rule.' if c=='Malaysia' else 'US rules require an unaltered original photograph.' if c=='USA' else '')) if c else 'Studio print profile.',url=sources.get(c,''),verification='Requires verification' if c else 'Studio preset') for n,w,h,c in rows]

class Database:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_root() / 'studio.db'
        self.conn = sqlite3.connect(self.path)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,name TEXT,payload TEXT,updated TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS profiles(name TEXT PRIMARY KEY,payload TEXT); CREATE TABLE IF NOT EXISTS exports(path TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);')
        if not self.get('profiles_initialized', False):
            for p in starter_profiles(): self.save_profile(p)
            self.set('profiles_initialized', True)

    def get(self, key, default=None):
        row = self.conn.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self,key,value):
        with self.conn: self.conn.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(key,json.dumps(value)))

    def save_job(self,job):
        with self.conn: self.conn.execute('INSERT OR REPLACE INTO jobs(id,name,payload,updated) VALUES(?,?,?,CURRENT_TIMESTAMP)',(job.id,job.name,json.dumps(job.to_dict())))

    def load_job(self,id):
        row=self.conn.execute('SELECT payload FROM jobs WHERE id=?',(id,)).fetchone()
        if not row: raise ValueError('Job no longer exists.')
        return Job.from_dict(json.loads(row[0]))

    def jobs(self):
        return self.conn.execute('SELECT id,name,updated FROM jobs ORDER BY updated DESC').fetchall()

    def profiles(self):
        return [json.loads(r[0]) for r in self.conn.execute('SELECT payload FROM profiles ORDER BY name')]

    def save_profile(self,p):
        if not p.get('name','').strip() or not 0<float(p['width'])<=1000 or not 0<float(p['height'])<=1000: raise ValueError('Enter a name and valid positive dimensions (up to 1000 mm).')
        with self.conn: self.conn.execute('INSERT OR REPLACE INTO profiles VALUES(?,?)',(p['name'],json.dumps(p)))

    def delete_profile(self,name):
        with self.conn: self.conn.execute('DELETE FROM profiles WHERE name=?',(name,))
