"""Local customer records; library UUIDs are validated cross-store references."""
import unicodedata
import uuid
from app.core.migrations import migrate,safety_snapshot


def normalized_mobile(value):
    value=unicodedata.normalize('NFKC',str(value or ''))
    digits=[]
    for char in value:
        try:digits.append(str(unicodedata.decimal(char)))
        except (ValueError,TypeError):pass
    return ''.join(digits)


def rows(cursor):
    keys=[c[0] for c in cursor.description]
    return [dict(zip(keys,row)) for row in cursor.fetchall()]


class CustomerStore:
    fields=('name','mobile','alternative_mobile','address','email','notes')

    def __init__(self,db):
        self.db=db;self.conn=db.conn
        self.conn.execute('PRAGMA foreign_keys=ON')
        if not self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='customers'").fetchone():safety_snapshot(db.path,'3.0-business')
        migrate(self.conn,1,[
            "CREATE TABLE customers(serial INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,name_search TEXT NOT NULL,mobile TEXT NOT NULL DEFAULT '',mobile_search TEXT NOT NULL DEFAULT '',alternative_mobile TEXT NOT NULL DEFAULT '',alternative_search TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP,activity TEXT DEFAULT CURRENT_TIMESTAMP,archived INTEGER NOT NULL DEFAULT 0)",
            'CREATE INDEX customers_name ON customers(name_search)',
            'CREATE INDEX customers_phone ON customers(mobile_search)',
            'CREATE INDEX customers_alt_phone ON customers(alternative_search)',
            'CREATE INDEX customers_activity ON customers(activity)',
            'CREATE TABLE customer_photo_links(customer_id TEXT REFERENCES customers(id) ON DELETE RESTRICT,photo_id TEXT NOT NULL,PRIMARY KEY(customer_id,photo_id))',
            'CREATE INDEX customer_photos_photo ON customer_photo_links(photo_id)',
            'CREATE TABLE customer_source_links(customer_id TEXT REFERENCES customers(id) ON DELETE RESTRICT,source_digest TEXT NOT NULL,PRIMARY KEY(customer_id,source_digest))',
            'CREATE TABLE customer_job_links(customer_id TEXT REFERENCES customers(id) ON DELETE RESTRICT,job_id TEXT REFERENCES jobs(id) ON DELETE RESTRICT,PRIMARY KEY(customer_id,job_id))'
        ])
        migrate(self.conn,4,['CREATE TABLE customer_photo_exclusions(customer_id TEXT REFERENCES customers(id) ON DELETE RESTRICT,photo_id TEXT NOT NULL,PRIMARY KEY(customer_id,photo_id))'])

    def save(self,values,customer_id=None):
        previous=self.get(customer_id) if customer_id else {}
        data={k:str(values.get(k,(previous or {}).get(k,''))).strip() for k in self.fields}
        if not data['name']:raise ValueError('Enter the customer name.')
        if any(len(v)>20000 for v in data.values()):raise ValueError('A customer field is too long.')
        data.update(name_search=unicodedata.normalize('NFKC',data['name']).casefold(),mobile_search=normalized_mobile(data['mobile']),alternative_search=normalized_mobile(data['alternative_mobile']))
        with self.conn:
            if customer_id:
                if not self.get(customer_id):raise ValueError('Customer no longer exists.')
                self.conn.execute('UPDATE customers SET '+','.join(k+'=?' for k in data)+',activity=CURRENT_TIMESTAMP WHERE id=?',(*data.values(),customer_id))
            else:
                customer_id=uuid.uuid4().hex
                self.conn.execute('INSERT INTO customers(id,'+','.join(data)+') VALUES('+','.join('?' for _ in range(len(data)+1))+')',(customer_id,*data.values()))
        return self.get(customer_id)

    def get(self,customer_id):
        found=rows(self.conn.execute('SELECT * FROM customers WHERE id=?',(customer_id,)))
        return found[0] if found else None

    def search(self,text='',archived=False,sort='activity',limit=200):
        text=unicodedata.normalize('NFKC',text).casefold().strip();phone=normalized_mobile(text)
        order={'name':'name_search','created':'created','activity':'activity'}.get(sort,'activity')
        return rows(self.conn.execute("SELECT * FROM customers WHERE archived=? AND (instr(name_search,?)>0 OR instr(lower(printf('C%06d',serial)),?)>0 OR (?<>'' AND (instr(mobile_search,?)>0 OR instr(alternative_search,?)>0))) ORDER BY "+order+(' ASC' if sort=='name' else ' DESC')+' LIMIT ?',(int(archived),text,text,phone,phone,phone,limit)))

    def duplicates(self,mobile,exclude=None):
        key=normalized_mobile(mobile)
        if not key:return []
        return rows(self.conn.execute('SELECT * FROM customers WHERE (mobile_search=? OR alternative_search=?) AND id<>?',(key,key,exclude or '')))

    def archive(self,customer_id,archived=True):
        with self.conn:self.conn.execute('UPDATE customers SET archived=? WHERE id=?',(int(archived),customer_id))

    def assign_photos(self,customer_id,photo_ids,tray):
        if not self.get(customer_id):raise ValueError('Select an existing customer.')
        requested=set(photo_ids);found={p.id for p in tray.by_ids(requested)}
        if requested!=found:raise ValueError('Restore missing/removed photos before assigning them.')
        with self.conn:
            self.conn.executemany('DELETE FROM customer_photo_exclusions WHERE customer_id=? AND photo_id=?',[(customer_id,p) for p in found])
            self.conn.executemany('INSERT OR IGNORE INTO customer_photo_links VALUES(?,?)',[(customer_id,p) for p in found])
            self.conn.execute('UPDATE customers SET activity=CURRENT_TIMESTAMP WHERE id=?',(customer_id,))

    def photo_ids(self,customer_id):return {r[0] for r in self.conn.execute('SELECT photo_id FROM customer_photo_links WHERE customer_id=?',(customer_id,))}
    def names_for_photo(self,photo_id):return ', '.join(r[0] for r in self.conn.execute('SELECT name FROM customers c JOIN customer_photo_links l ON l.customer_id=c.id WHERE l.photo_id=?',(photo_id,)))
    def matching_photo_ids(self,text):
        customers=self.search(text)
        ids=set()
        for customer in customers:ids.update(self.photo_ids(customer['id']))
        return ids

    def unlink_photos(self,customer_id,photo_ids):
        with self.conn:
            self.conn.executemany('DELETE FROM customer_photo_links WHERE customer_id=? AND photo_id=?',[(customer_id,p) for p in photo_ids])
            self.conn.executemany('INSERT OR IGNORE INTO customer_photo_exclusions VALUES(?,?)',[(customer_id,p) for p in photo_ids])

    def assign_sources(self,customer_id,paths,tray):
        """Persist intent before crops exist; repeating a source assignment is safe."""
        if not customer_id:self.reconcile(tray);return
        if not self.get(customer_id):raise ValueError('Customer no longer exists.')
        with tray.lock:
            digests=[r[0] for path in paths for r in tray.conn.execute('SELECT digest FROM sources WHERE asset=?',(path,))]
        with self.conn:self.conn.executemany('INSERT OR IGNORE INTO customer_source_links VALUES(?,?)',[(customer_id,d) for d in digests])
        self.reconcile(tray)

    def reconcile(self,tray):
        """Recover interrupted post-crop association without changing the library."""
        if not tray.conn:return
        # Idempotent repair journal bridges the worker-owned library and GUI-owned
        # main store. A crash between commits leaves the journal for the next run.
        with tray.lock:repairs=tray.conn.execute('SELECT old,new FROM source_repairs').fetchall()
        if repairs:
            import json
            def remap(value):
                if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
                if isinstance(value,list):return [remap(v) for v in value]
                if isinstance(value,str):
                    return next((new for old,new in repairs if value.casefold()==old.casefold()),value)
                return value
            clean=True
            with self.conn:
                for table,field in [('jobs','payload'),('order_items','snapshot')]:
                    if not self.conn.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():continue
                    for id,raw in self.conn.execute(f'SELECT id,{field} FROM {table}').fetchall():
                        try:updated=json.dumps(remap(json.loads(raw)))
                        except (ValueError,TypeError):clean=False;continue
                        self.conn.execute(f'UPDATE {table} SET {field}=? WHERE id=?',(updated,id))
            if clean:
                with tray.lock,tray.conn:tray.conn.execute('DELETE FROM source_repairs')
        additions=[]
        with tray.lock:
            for customer_id,digest in self.conn.execute('SELECT customer_id,source_digest FROM customer_source_links'):
                additions.extend((customer_id,r[0]) for r in tray.conn.execute('SELECT p.id FROM photos p JOIN sources s ON p.source=s.asset WHERE s.digest=?',(digest,)))
        with self.conn:
            for customer_id,photo_id in additions:self.conn.execute('INSERT OR IGNORE INTO customer_photo_links SELECT ?,? WHERE NOT EXISTS(SELECT 1 FROM customer_photo_exclusions WHERE customer_id=? AND photo_id=?)',(customer_id,photo_id,customer_id,photo_id))
