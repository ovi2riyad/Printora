"""Exact millimetre layouts; no implicit photo rotation or size changes."""
import copy
import math
from collections import defaultdict
from app.models.domain import Placement


def mm_to_pt(mm):
    return mm * 72 / 25.4


def page_size(settings):
    return (297., 210.) if settings.get('landscape') else (210., 297.)


def geometry(settings):
    pw, ph = page_size(settings)
    margin = float(settings.get('margin', 10))
    gx, gy = float(settings.get('gap_x', 2)), float(settings.get('gap_y', 3))
    if not all(math.isfinite(v) and v >= 0 for v in (margin, gx, gy)) or 2 * margin >= min(pw, ph):
        raise ValueError('Page margins must leave printable space; gaps cannot be negative.')
    return pw, ph, margin, gx, gy


def layout_capacity(photo, settings):
    pw, ph, m, gx, gy = geometry(settings)
    photo.validate()
    columns = math.floor((pw - 2*m + gx + 1e-8) / (photo.width + gx))
    rows = math.floor((ph - 2*m + gy + 1e-8) / (photo.height + gy))
    if not columns or not rows:
        raise ValueError(f'{photo.width:g} × {photo.height:g} mm does not fit A4 with {m:g} mm margins. Try landscape paper, smaller margins, or an explicitly smaller photo size.')
    mode = settings.get('layout', 'auto')
    if mode in ('grid_2x2', 'custom'):
        columns_wanted, rows_wanted = (2, 2) if mode == 'grid_2x2' else (settings.get('columns', 2), settings.get('rows', 2))
        if any(not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 100 for v in (columns_wanted, rows_wanted)):
            raise ValueError('Choose whole rows and columns between 1 and 100.')
        if columns_wanted > columns or rows_wanted > rows:
            raise ValueError(f'Requested {columns_wanted} columns × {rows_wanted} rows will not fit without resizing. This page fits up to {columns} columns × {rows} rows at {photo.width:g} × {photo.height:g} mm. Use Maximum-fit, landscape paper, or reduce margins/gaps.')
        return columns_wanted, rows_wanted
    if mode not in ('auto', 'max_fit'):
        raise ValueError('Choose Automatic, 2 × 2, Custom, or Maximum-fit.')
    return columns, rows


def auto_layout(photos, settings):
    pw, ph, m, gx, gy = geometry(settings)
    if settings.get('layout', 'auto') != 'auto':
        result, page = [], 0
        for photo in photos:
            columns, rows = layout_capacity(photo, settings)
            count = columns * rows
            block_w = columns*photo.width + (columns-1)*gx
            block_h = rows*photo.height + (rows-1)*gy
            x0, y0 = (pw-block_w)/2, (ph-block_h)/2
            for number in range(photo.quantity):
                slot = number % count
                result.append(Placement(photo.id, number, page+number//count,
                                        x0+(slot % columns)*(photo.width+gx),
                                        y0+(slot//columns)*(photo.height+gy), photo.width, photo.height))
            page += math.ceil(photo.quantity/count)
        return result
    result, row = [], []
    used, rh, y, page = 0., 0., m, 0

    def flush():
        nonlocal row, used, rh, y, page
        if not row:return
        if y+rh > ph-m+1e-8:
            page += 1
            y = m
        x = (pw-used)/2
        for photo, number in row:
            result.append(Placement(photo.id, number, page, x, y, photo.width, photo.height))
            x += photo.width+gx
        y += rh+gy
        row, used, rh = [], 0., 0.

    for photo in photos:
        layout_capacity(photo, settings)
        for number in range(photo.quantity):
            if row and used+gx+photo.width > pw-2*m+1e-8:flush()
            used += (gx if row else 0)+photo.width
            rh = max(rh, photo.height)
            row.append((photo, number))
    flush()
    return result


def overlaps(a, b):
    return (a.page == b.page and min(a.x+a.width, b.x+b.width)-max(a.x, b.x) > 1e-7
            and min(a.y+a.height, b.y+b.height)-max(a.y, b.y) > 1e-7)


def resize_copies(job):
    """Keep existing copy coordinates; place new copies only in free grid slots."""
    if not job.placements:return
    ids = {p.id: p for p in job.photos}
    kept = [r for r in job.placements if r.photo_id in ids and r.copy < ids[r.photo_id].quantity]
    seen = {(r.photo_id, r.copy) for r in kept}
    candidates = auto_layout(job.photos, job.print_settings)
    per_page = defaultdict(list)
    for r in kept:per_page[r.page].append(r)
    slots_by_photo={}
    for candidate in candidates:
        if candidate.photo_id not in slots_by_photo:slots_by_photo[candidate.photo_id]=(candidate.page,[])
        first_page,slots=slots_by_photo[candidate.photo_id]
        if candidate.page==first_page:slots.append(candidate)
    cursors=defaultdict(int)
    for candidate in candidates:
        if (candidate.photo_id, candidate.copy) in seen:continue
        _,slots=slots_by_photo[candidate.photo_id]
        placed = None
        while placed is None:
            position=cursors[candidate.photo_id];page,slot_index=divmod(position,len(slots));slot=slots[slot_index];cursors[candidate.photo_id]+=1
            probe=copy.copy(candidate);probe.x,probe.y,probe.page=slot.x,slot.y,page
            if not any(overlaps(probe,r) for r in per_page[page]):placed=probe
        kept.append(placed)
        per_page[placed.page].append(placed)
        seen.add((placed.photo_id, placed.copy))
    job.placements = sorted(kept, key=lambda r: (r.page, r.photo_id, r.copy))
    job.page_count = max((r.page+1 for r in kept), default=1)


def validate_layout(job):
    pw, ph, margin, _, _ = geometry(job.print_settings)
    margin = margin if job.print_settings.get('enforce_margins', False) else 0
    ids, seen, pages = {p.id:p for p in job.photos}, set(), defaultdict(list)
    for p in job.photos:p.validate()
    for r in job.placements:
        p = ids.get(r.photo_id)
        if p is None or not 0 <= r.copy < p.quantity:
            raise ValueError('Layout contains an invalid copy. Reset automatic layout.')
        if (r.photo_id, r.copy) in seen:raise ValueError('Layout contains duplicate copies.')
        seen.add((r.photo_id, r.copy))
        if abs(r.width-p.width)>1e-7 or abs(r.height-p.height)>1e-7:
            raise ValueError('Photo size changed. Reset automatic layout.')
        if (r.page < 0 or r.page >= job.page_count or not all(math.isfinite(v) for v in (r.x,r.y,r.width,r.height))
                or r.x < margin-1e-7 or r.y < margin-1e-7
                or r.x+r.width > pw-margin+1e-7 or r.y+r.height > ph-margin+1e-7):
            raise ValueError('A photograph extends beyond the page or configured margins.')
        pages[r.page].append(r)
    if len(seen) != sum(p.quantity for p in job.photos):
        raise ValueError('Layout is missing copies. Reset automatic layout.')
    # Sweep each page instead of comparing unrelated pages and rows.
    for placements in pages.values():
        active = []
        for r in sorted(placements, key=lambda p:p.y):
            active = [p for p in active if p.y+p.height > r.y+1e-7]
            if any(overlaps(r,p) for p in active):
                raise ValueError('Photographs overlap. Move them apart before exporting.')
            active.append(r)
