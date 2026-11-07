"""Atomic recipe JSON exports that fail closed around original assets."""
import json
import os
from pathlib import Path
import tempfile
from app.services.export_safety import check_export_target
from app.services.storage import layer_assets


def original_assets(conn):
    """Include saved/session jobs and historical order-only images, not config."""
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    protected=set()
    for table,column in (('jobs','payload'),('order_items','snapshot')):
        if table not in tables:continue
        for id,raw in conn.execute(f'SELECT id,{column} FROM {table}'):
            try:
                document=json.loads(raw)
                if not isinstance(document,dict):raise ValueError('expected an object')
                protected.update(layer_assets(document))
            except (ValueError,TypeError,AttributeError,RecursionError) as error:
                raise ValueError(f'Cannot verify original photo references in {table} record {id}. Export canceled; the record was retained.') from error
    return protected


def recipe_target(db,path):
    chosen=Path(path)
    if chosen.suffix.lower()!='.json' or ':' in chosen.name:
        raise ValueError('Choose a .json filename for recipe exports. The selected filename was not changed.')
    if chosen.is_symlink():raise ValueError('Choose a regular JSON file, not a file shortcut or symbolic link.')
    protected=original_assets(db.conn)
    target=check_export_target(chosen,db.path.parent,db.conn,protected)
    if target.exists():
        for original in protected:
            if original.exists() and target.samefile(original):
                raise ValueError('Choose a new filename to preserve the original photo file.')
        # Protect even unsaved/untracked photos disguised with a JSON extension.
        try:
            with target.open(encoding='utf-8-sig') as stream:json.load(stream)
        except (ValueError,UnicodeError) as error:
            raise ValueError('The selected file contains non-JSON data and will not be overwritten. Choose a new .json filename.') from error
    return target


def export_recipes(db,path):
    target=recipe_target(db,path)
    payload=json.dumps(db.profiles(),indent=2)
    # Use an exclusive sibling temporary file; never truncate the selected target.
    fd,temporary=tempfile.mkstemp(prefix='.printora-recipes-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        if recipe_target(db,path)!=target:
            raise ValueError('The export destination changed while saving. Choose a stable destination and retry.')
        os.replace(temporary,target)
    finally:Path(temporary).unlink(missing_ok=True)
    return str(target)
