"""Explicit cleanup of owned abandoned temporary sessions and expired helper requests."""
from pathlib import Path
import json,re,shutil,time

def cleanup_temporary(root,protected=(),active=(),days=7):
    if not 1<=days<=365:raise ValueError('Retention must be 1–365 days')
    root=Path(root).resolve();protected=[Path(p).resolve() for p in protected];active={Path(p).resolve() for p in active}
    removed=0
    for name in ('hardware-requests','document-sessions'):
        parent=root/name
        if not parent.exists():continue
        if parent.is_symlink() or parent.is_junction():raise ValueError('Cleanup does not traverse linked directories')
        for folder in parent.iterdir():
            if not folder.is_dir() or folder.is_symlink() or folder.is_junction() or not re.fullmatch('[0-9a-f]{32}',folder.name):continue
            resolved=folder.resolve()
            if resolved.parent!=parent or resolved in active or any(p.is_relative_to(resolved) for p in protected):continue
            if folder.stat().st_mtime>time.time()-days*86400:continue
            if name=='document-sessions':
                marker=folder/'session.json'
                try:record=json.loads(marker.read_text(encoding='utf-8'))
                except (ValueError,OSError):continue
                if record.get('keep') is not False or record.get('kind') not in ('copy','nid'):continue
            elif any(p.name not in ('request.json','result.json') for p in folder.iterdir()):continue
            shutil.rmtree(resolved);removed+=1
    return removed
