"""Persistent submission uncertainty guard, independent of UI lifetime.

A driver submission is not physical completion. Unknown ledgers require an
operator's queue check and acknowledgment; no code retries a transaction.
"""
from pathlib import Path
import json
import os

def unresolved(root):
    rows=[]
    for path in (Path(root)/'print-spool').glob('*/status.json'):
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            status=str(record.get('status',''))
            if status.startswith('submitted to driver') or status in ('SubmittedToDriver','SubmissionFailed'):continue
            review=path.parent/'queue-reviewed.json'
            if not review.exists():rows.append(path)
            else:
                acknowledgment=json.loads(review.read_text(encoding='utf-8'))
                if not isinstance(acknowledgment,dict) or acknowledgment.get('operator_checked_queue') is not True or acknowledgment.get('retry_automatic') is not False:rows.append(path)
        except (OSError,ValueError,AttributeError):rows.append(path)
    return rows

def acknowledge(paths):
    for path in paths:
        target=Path(path).parent/'queue-reviewed.json'
        # Never modify the submission ledger or infer a successful print.
        with target.open('x',encoding='utf-8') as f:
            json.dump({'operator_checked_queue':True,'retry_automatic':False},f);f.flush();os.fsync(f.fileno())

def profile_key(job,color='color'):
    from app.services.layout import page_size
    w,h=page_size(job.print_settings)
    # A saved confirmation cannot authorize a different paper footprint or scaling.
    if color not in ('color','gray'):raise ValueError('Invalid printer color mode')
    return f'{w:.3f}x{h:.3f}:actual-size:{color}'

def repeat_sheets(job,sets):
    import copy
    from app.services.layout import validate_layout
    if type(sets) is not int or not 1<=sets<=100:raise ValueError('Choose 1–100 sheet sets')
    result=copy.deepcopy(job);result.placements=[]
    quantities={p.id:p.quantity for p in job.photos}
    for n in range(sets):
        for r in job.placements:
            item=copy.deepcopy(r);item.page+=n*job.page_count;item.copy+=n*quantities[r.photo_id];result.placements.append(item)
    for p in result.photos:p.quantity*=sets
    result.page_count*=sets;validate_layout(result);return result
