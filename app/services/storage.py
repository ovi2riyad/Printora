"""Local verified backups, staged restore, and reference-aware cache maintenance."""
from datetime import datetime
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile


def _readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def referenced_assets(root):
    """Parse all jobs, including jobs not currently open. Fail closed on corruption."""
    result = set()
    path = Path(root) / 'studio.db'
    if path.exists():
        with closing(_readonly(path)) as conn:
            for (payload,) in conn.execute('SELECT payload FROM jobs'):
                for photo in json.loads(payload).get('photos', []):
                    for layer in photo.get('layers', []):
                        for key in ('source', 'mask'):
                            if layer.get(key):result.add(Path(layer[key]).resolve())
    return result


def storage_usage(root):
    root = Path(root)
    total = library = 0
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink():
            size = path.stat().st_size
            total += size
            if path.is_relative_to(root/'library'):library += size
    return dict(total=total, library=library)


def backup_data(root, destination, include_models=False):
    """SQLite backup API includes WAL transactions; originals/assets are byte copies."""
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.is_relative_to(root):
        raise ValueError('Save the backup outside the application-data folder.')
    if not (root/'studio.db').is_file():raise ValueError('The application database is missing.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='studio-backup-') as temporary:
        snapshot = Path(temporary)
        files, external = {}, {}
        for path in root.rglob('*'):
            if path.is_symlink():raise ValueError('Backups do not follow symbolic links: '+str(path))
            if not path.is_file() or path.name.endswith(('-wal','-shm','.tmp','.download')):continue
            relative = path.relative_to(root)
            if not include_models and relative.parts[0]=='models':continue
            if path.suffix=='.db':
                saved = snapshot/relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                source = _readonly(path)
                target = sqlite3.connect(saved)
                try:source.backup(target)
                finally:source.close();target.close()
                files[relative.as_posix()] = saved
            else:files[relative.as_posix()] = path
        # Older jobs can reference files outside app data; include these too.
        for asset in referenced_assets(root):
            if not asset.is_file():raise ValueError('A saved job references a missing image: '+str(asset))
            if not asset.is_relative_to(root):
                if not asset.is_file():raise ValueError('A saved job references a missing external image: '+str(asset))
                name = 'restored_external/'+hashlib.sha256(str(asset).encode()).hexdigest()[:24]+'/'+asset.name
                files[name] = asset
                external[str(asset)] = name
        manifest = dict(format=1, source_root=str(root), external=external, includes_models=include_models, files={})
        fd, temporary_zip = tempfile.mkstemp(prefix=destination.stem+'-', suffix='.tmp', dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
                for name, path in sorted(files.items()):
                    digest = hashlib.sha256()
                    with path.open('rb') as stream, archive.open(name, 'w', force_zip64=True) as output:
                        while block := stream.read(1024*1024):digest.update(block);output.write(block)
                    manifest['files'][name] = dict(sha256=digest.hexdigest(), bytes=path.stat().st_size)
                archive.writestr('backup-manifest.json', json.dumps(manifest, indent=2))
            os.replace(temporary_zip, destination)
        finally:
            if Path(temporary_zip).exists():Path(temporary_zip).unlink()
    return str(destination)


def _safe_name(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or str(p)!=name:
        raise ValueError('Unsafe path in backup: '+name)
    return p


def _remap(value, old_root, new_root, external):
    if isinstance(value, dict):return {k:_remap(v,old_root,new_root,external) for k,v in value.items()}
    if isinstance(value, list):return [_remap(v,old_root,new_root,external) for v in value]
    if not isinstance(value, str):return value
    for path, relative in external.items():
        if value.casefold()==path.casefold():return str(new_root/relative)
    normalized, prefix = value.replace('\\','/'), old_root.replace('\\','/').rstrip('/')
    if normalized.casefold()==prefix.casefold():return str(new_root)
    if normalized.casefold().startswith(prefix.casefold()+'/'):
        suffix = normalized[len(prefix)+1:]
        _safe_name(suffix)
        return str(new_root/suffix)
    return value


def prepare_restore(archive_path, destination):
    """Verify into a sibling staging folder. Never touch current production files."""
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=destination.name+'.restore-', dir=destination.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            if len(archive.infolist())>500000:raise ValueError('Backup contains too many entries.')
            manifest = json.loads(archive.read('backup-manifest.json'))
            if manifest.get('format')!=1 or 'studio.db' not in manifest.get('files', {}):
                raise ValueError('Choose a Studio Photo Maker backup ZIP.')
            names = archive.namelist()
            expected = set(manifest['files'])|{'backup-manifest.json'}
            if len(names)!=len(set(names)) or set(names)!=expected:
                raise ValueError('Backup contents do not match its manifest.')
            required = sum(i.file_size for i in archive.infolist())
            if required > shutil.disk_usage(stage).free:
                raise ValueError('Not enough free disk space to restore this backup.')
            for name, expected_info in manifest['files'].items():
                _safe_name(name)
                info = archive.getinfo(name)
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symbolic links are not supported in backups.')
                target = stage/name
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(name) as source, target.open('wb') as output:
                    while block := source.read(1024*1024):digest.update(block);output.write(block)
                if target.stat().st_size!=expected_info['bytes'] or digest.hexdigest()!=expected_info['sha256']:
                    raise ValueError('Backup integrity check failed: '+name)
        for relative in manifest.get('external', {}).values():_safe_name(relative)
        old = manifest['source_root']
        external = manifest.get('external', {})
        # A backup can omit re-downloadable models; retain already-installed models.
        if not manifest.get('includes_models') and (destination/'models').is_dir():
            shutil.copytree(destination/'models',stage/'models',dirs_exist_ok=True)
        main = sqlite3.connect(stage/'studio.db')
        try:
            if main.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Damaged job database in backup.')
            with main:
                for table, key, field in [('jobs','id','payload'),('config','key','value'),('profiles','name','payload')]:
                    for id, raw in main.execute(f'SELECT {key},{field} FROM {table}').fetchall():
                        rewritten = _remap(json.loads(raw),old,destination,external)
                        main.execute(f'UPDATE {table} SET {field}=? WHERE {key}=?',(json.dumps(rewritten),id))
                for (path,) in main.execute('SELECT path FROM exports').fetchall():
                    main.execute('UPDATE exports SET path=? WHERE path=?',(_remap(path,old,destination,external),path))
        finally:main.close()
        library_path = stage/'library'/'library.db'
        if library_path.exists():
            library = sqlite3.connect(library_path)
            try:
                if library.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Damaged library database in backup.')
                with library:
                    for table, fields in [('photos',('source','asset','thumb')),('sources',('asset',)),('source_regions',('asset',))]:
                        for field in fields:
                            for rowid, value in library.execute(f'SELECT rowid,{field} FROM {table}').fetchall():
                                library.execute(f'UPDATE {table} SET {field}=? WHERE rowid=?',(_remap(value,old,destination,external),rowid))
            finally:library.close()
        (stage/'restore-ready.json').write_text(json.dumps(dict(destination=str(destination),files=len(manifest['files']))),encoding='utf-8')
        return str(stage)
    except Exception:
        # Only our newly created, resolved staging directory is removed.
        if stage.parent==destination.parent and stage.name.startswith(destination.name+'.restore-'):
            shutil.rmtree(stage)
        raise


def install_restore(stage, destination):
    """Call only after closing both databases/workers. Retain the whole old folder."""
    stage, destination = Path(stage).resolve(), Path(destination).resolve()
    if stage.parent!=destination.parent or not stage.name.startswith(destination.name+'.restore-'):
        raise ValueError('Restore staging folder is outside the application-data parent.')
    ready = json.loads((stage/'restore-ready.json').read_text(encoding='utf-8'))
    if Path(ready['destination']).resolve()!=destination:raise ValueError('Restore target does not match the verified backup.')
    previous = destination.with_name(destination.name+'.before-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    journal=destination.with_name(destination.name+'.restore-pending.json')
    if journal.exists():raise ValueError('An earlier restore must be recovered before starting another.')
    fd,temporary_journal=tempfile.mkstemp(prefix=destination.name+'.restore-journal-',suffix='.tmp',dir=destination.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(dict(stage=str(stage),destination=str(destination),previous=str(previous)),stream);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary_journal,journal)
    finally:
        if Path(temporary_journal).exists():Path(temporary_journal).unlink()
    if destination.exists():destination.rename(previous)
    try:stage.rename(destination)
    except Exception:
        if previous.exists():previous.rename(destination)
        if destination.exists():journal.unlink()
        raise
    journal.unlink()
    return str(previous)


def recover_restore(destination):
    """Finish/roll back a directory swap interrupted by process or power loss."""
    destination=Path(destination).resolve();journal=destination.with_name(destination.name+'.restore-pending.json')
    if not journal.exists():return
    saved=json.loads(journal.read_text(encoding='utf-8'));stage=Path(saved['stage']).resolve();previous=Path(saved['previous']).resolve()
    if (Path(saved['destination']).resolve()!=destination or stage.parent!=destination.parent
            or previous.parent!=destination.parent or not stage.name.startswith(destination.name+'.restore-')
            or not previous.name.startswith(destination.name+'.before-restore-')):
        raise ValueError('Restore journal contains unexpected paths. Preserve all data folders and inspect the journal.')
    if not destination.exists():
        if stage.exists():
            ready=json.loads((stage/'restore-ready.json').read_text(encoding='utf-8'))
            if Path(ready['destination']).resolve()!=destination:raise ValueError('Interrupted restore target mismatch.')
            stage.rename(destination)
        elif previous.exists():previous.rename(destination)
        else:raise ValueError('Interrupted restore needs manual recovery; data folders were not found.')
    journal.unlink()


def discard_restore(stage,destination):
    stage,destination=Path(stage).resolve(),Path(destination).resolve()
    if stage.parent!=destination.parent or not stage.name.startswith(destination.name+'.restore-'):
        raise ValueError('Unexpected restore staging path.')
    ready=json.loads((stage/'restore-ready.json').read_text(encoding='utf-8'))
    if Path(ready['destination']).resolve()!=destination:raise ValueError('Restore target mismatch.')
    shutil.rmtree(stage)


def clear_safe_cache(root, extra_references=(), older_than_seconds=86400):
    root = Path(root).resolve()
    protected = referenced_assets(root)|{Path(p).resolve() for p in extra_references if p}
    count = size = 0
    cache = root/'cache'
    if cache.exists():
        for path in cache.iterdir():
            if path.is_symlink() or not path.is_file() or path.resolve() in protected:continue
            if path.suffix not in ('.png','.tmp','.download') or time.time()-path.stat().st_mtime<older_than_seconds:continue
            size += path.stat().st_size
            path.unlink()
            count += 1
    return dict(files=count, bytes=size)
