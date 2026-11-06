"""Protect application assets and previous successful order artifacts in UI exports."""
from pathlib import Path


def check_export_target(path,root,conn,protected=()):
    target=Path(path).resolve()
    if target.is_relative_to(Path(root).resolve()) or target in {Path(p).resolve() for p in protected if p}:
        raise ValueError('Choose an export location outside application data and original photo files.')
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='print_events'").fetchone():
        if conn.execute("SELECT 1 FROM print_events WHERE path=? COLLATE NOCASE AND status='Ready'",(str(target),)).fetchone():raise ValueError('Choose a new filename to preserve the previous order PDF.')
    return target
