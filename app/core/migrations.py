"""Small additive migrations and one-time pre-upgrade SQLite safety snapshots."""
from pathlib import Path
import sqlite3
import time


def safety_snapshot(path, version):
    path=Path(path)
    if not path.exists():return
    folder=path.parent/(path.stem+'-upgrade-snapshots');folder.mkdir(exist_ok=True)
    target=folder/f'before-{version}.db'
    if target.exists():return
    temporary=target.with_suffix('.tmp')
    source=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    dest=sqlite3.connect(temporary)
    try:source.backup(dest)
    finally:dest.close();source.close()
    temporary.replace(target)


def migrate(conn, version, sql):
    conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied TEXT DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    if conn.execute('SELECT 1 FROM schema_migrations WHERE version=?',(version,)).fetchone():return
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM schema_migrations WHERE version=?',(version,)).fetchone():return
        for statement in sql:conn.execute(statement)
        conn.execute('INSERT INTO schema_migrations(version) VALUES(?)',(version,))
