import math
from app.models.domain import Placement

def mm_to_pt(mm): return mm * 72 / 25.4

def page_size(settings): return (297.,210.) if settings.get('landscape') else (210.,297.)

def auto_layout(photos,settings):
    pw,ph=page_size(settings)
    m=float(settings.get('margin',10)); gx=float(settings.get('gap_x',2)); gy=float(settings.get('gap_y',3))
    if not all(math.isfinite(v) and v>=0 for v in (m,gx,gy)) or 2*m>=min(pw,ph): raise ValueError('Invalid page margins or spacing.')
    result=[]; row=[]; used=0.; rh=0.; y=m; page=0
    def flush():
        nonlocal row,used,rh,y,page
        if not row:return
        if y+rh>ph-m+1e-8: page+=1; y=m
        x=(pw-used)/2
        for photo,copy in row:
            result.append(Placement(photo.id,copy,page,x,y,photo.width,photo.height)); x+=photo.width+gx
        y+=rh+gy; row=[]; used=0.; rh=0.
    for photo in photos:
        photo.validate()
        if photo.width>pw-2*m+1e-8 or photo.height>ph-2*m+1e-8: raise ValueError(f'{photo.name}: {photo.width} x {photo.height} mm cannot fit inside the page margins.')
        for i in range(photo.quantity):
            if row and used+gx+photo.width>pw-2*m+1e-8:flush()
            used+=(gx if row else 0)+photo.width; rh=max(rh,photo.height); row.append((photo,i))
    flush()
    return result

def validate_layout(job):
    pw,ph=page_size(job.print_settings); ids={p.id:p for p in job.photos}; seen=set()
    for r in job.placements:
        p=ids.get(r.photo_id)
        if p is None or not 0<=r.copy<p.quantity: raise ValueError('Layout contains an invalid copy. Reset automatic layout.')
        if (r.photo_id,r.copy) in seen: raise ValueError('Layout contains duplicate copies.')
        seen.add((r.photo_id,r.copy))
        if abs(r.width-p.width)>1e-7 or abs(r.height-p.height)>1e-7: raise ValueError('Photo size changed. Reset automatic layout.')
        if r.page<0 or r.page>=job.page_count or not all(math.isfinite(v) for v in (r.x,r.y,r.width,r.height)) or r.x<0 or r.y<0 or r.x+r.width>pw+1e-7 or r.y+r.height>ph+1e-7: raise ValueError('A photograph extends beyond the page.')
    if len(seen)!=sum(p.quantity for p in job.photos): raise ValueError('Layout is missing copies. Reset automatic layout.')
    for i,a in enumerate(job.placements):
        for b in job.placements[i+1:]:
            if a.page==b.page and min(a.x+a.width,b.x+b.width)-max(a.x,b.x)>0.01 and min(a.y+a.height,b.y+b.height)-max(a.y,b.y)>0.01: raise ValueError('Photographs overlap. Move them apart before exporting.')
