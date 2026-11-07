"""Hardware contracts and source preservation; no GUI or driver imports."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import uuid
from PIL import Image

HARDWARE_DEFAULTS = dict(scan_area_presets={},scanner_id='', scanner_backend='wia', scan_dpi=300,
                         scan_color='color', scan_source='', preferred_printer='',scan_region=[],scanner_fallbacks={},document_paper='A4',document_paper_mm=[210,297],document_landscape=False,document_color='color',quick_print=False,confirmed_print_profiles={},preferred_print_color='color')


def validate_hardware_setting(key, value):
    if key=='scan_area_presets':
        if not isinstance(value,dict) or len(value)>100:raise ValueError('Save at most 100 named scan areas')
        for name,preset in value.items():
            if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 for c in name):raise ValueError('Invalid scan-area name')
            if not isinstance(preset,dict) or set(preset)!={'device','source','region'}:raise ValueError('Invalid saved scan area')
            for field in ('device','source'):
                if not isinstance(preset[field],str) or not preset[field] or len(preset[field])>2048 or '\x00' in preset[field]:raise ValueError('Invalid scan-area scanner/source')
            validate_hardware_setting('scan_region',preset['region'])
            if len(preset['region'])!=4 or min(preset['region'][2:])<1:raise ValueError('Saved scan area must be at least 1 mm')
        return value
    if key=='quick_print':
        if type(value) is not bool:raise ValueError('Quick Print must be enabled explicitly')
        return value
    if key=='confirmed_print_profiles':
        if not isinstance(value,dict) or len(value)>100 or any(not isinstance(k,str) or not isinstance(v,list) or len(k)>2048 or len(v)>100 or any(not isinstance(p,str) or len(p)>200 for p in v) for k,v in value.items()):raise ValueError('Invalid saved printer confirmations')
        return value
    if key=='document_landscape':
        if type(value) is not bool:raise ValueError('Document orientation must be a boolean')
        return value
    if key=='preferred_print_color':
        if value not in ('color','gray'):raise ValueError('Invalid saved driver color mode')
        return value
    if key=='document_color':
        if value not in ('color','gray','mono'):raise ValueError('Invalid document color mode')
        return value
    if key=='document_paper_mm':
        if not isinstance(value,list) or len(value)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 50<=v<=1000 for v in value):raise ValueError('Invalid saved document paper')
        return value
    if key=='scanner_fallbacks':
        if not isinstance(value,dict) or len(value)>100 or any(not isinstance(k,str) or not isinstance(v,str) or not k or not v or len(k)>2048 or len(v)>2048 for k,v in value.items()):raise ValueError('Invalid scanner fallback bindings')
        return value
    if key=='scan_region':
        if not isinstance(value,list) or len(value) not in (0,4) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000 for v in value):raise ValueError('Invalid saved scanner region')
        return value
    if key == 'scan_dpi':
        if type(value) is not int or not 50 <= value <= 9600:
            raise ValueError('Scan DPI must be a whole number from 50 to 9600')
    elif key == 'scanner_backend':
        if value not in ('wia','twain32','twain64'):
            raise ValueError('Only the installed WIA acquisition backend is enabled')
    elif key == 'scan_color':
        if value not in ('color', 'gray'):
            raise ValueError('Choose color or grayscale')
    elif not isinstance(value, str) or '\x00' in value or len(value) > 2048:
        raise ValueError('Invalid device identifier')
    return value


class ScannerBackend:
    name = ''

    def request(self, action, **settings):
        raise NotImplementedError


class WiaBackend(ScannerBackend):
    name = 'wia'

    def request(self, action, **settings):
        if action not in ('devices', 'capabilities', 'scan'):
            raise ValueError('Unsupported scanner operation')
        return dict(action=action, **settings)

class TwainBackend(WiaBackend):
    name='twain32'
    def request(self,action,**settings):
        if action=='scan' and settings.get('max_pages',1)!=1:raise ValueError('TWAIN feeder batches are not enabled; choose one page or a supported WIA feeder')
        return super().request(action,**settings)

def safe_fallback(started,alternative_verified,attempts):
    return not started and bool(alternative_verified) and attempts==0


class ScannerManager:
    """No implicit retry or cross-backend fallback after a failed acquisition."""
    def __init__(self, backend=None):
        self.backend = backend;self.backends={'wia':WiaBackend(),'twain32':TwainBackend()}

    def request(self, action, **settings):
        backend=self.backend or self.backends['twain32' if str(settings.get('device','')).startswith('twain32:') else 'wia']
        return backend.request(action, **settings)


def new_scan_folder(root,direct=False):
    folder = (Path(root) if direct else Path(root) / 'scans') / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def inspect_scan(path, folder, provenance):
    """Verify driver bytes without decoding/re-encoding the retained original."""
    path, folder = Path(path).resolve(), Path(folder).resolve()
    if path.parent != folder or not path.is_file() or path.is_symlink():
        raise ValueError('Scanner returned a file outside its acquisition folder')
    with Image.open(path) as image:
        width, height = image.size
        if getattr(image,'n_frames',1)!=1:raise ValueError('Driver returned a multi-frame image for one requested page. Original retained; review outside automatic copy.')
        if width <= 0 or height <= 0 or width * height > 80_000_000:
            raise ValueError('Scan exceeds the 80 megapixel inspection limit; original retained')
        info = dict(width=width, height=height, format=image.format, mode=image.mode,
                    metadata_dpi=image.info.get('dpi'))
        image.verify()
    # BMP's verify() alone does not read its pixel data. Decode in this isolated
    # worker, within the explicit pixel budget, so truncated transfers fail too.
    with Image.open(path) as image:
        image.load()
    with path.open('rb') as original:
        digest = hashlib.file_digest(original, 'sha256').hexdigest()
    record = dict(provenance, **info, sha256=digest, original=str(path))
    # Only this operation owns this fresh folder; never replace an existing record.
    with (folder / 'provenance.json').open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
    return record


def inspect_scans(folder,pages,provenance):
    """Validate a bounded feeder result without losing successful earlier pages."""
    folder=Path(folder).resolve()
    if not isinstance(pages,list) or not 1<=len(pages)<=100:raise ValueError('Invalid feeder page list')
    records=[];seen=set()
    for page in pages:
        path=Path(page['path']).resolve()
        if path.parent.parent!=folder or path in seen or not path.parent.name.startswith('page-'):raise ValueError('Feeder returned an unsafe or duplicate page')
        seen.add(path);records.append(inspect_scan(path,path.parent,provenance))
    result=dict(records[0]);result['pages']=records;return result


def check_scan_request(caps, dpi, color, region):
    validate_hardware_setting('scan_dpi', dpi)
    if dpi not in caps['resolutions']:
        raise ValueError('This driver does not report the requested resolution')
    if color not in caps['colors']:
        raise ValueError('This driver does not report the requested color mode')
    if len(region) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in region):
        raise ValueError('Invalid scan region')
    x, y, width, height = region
    if min(x, y) < 0 or min(width, height) <= 0:
        raise ValueError('Invalid scan region')
    if x + width > caps['width_mm'] + .1 or y + height > caps['height_mm'] + .1:
        raise ValueError('Scan region extends beyond the reported scan bed')
    if width * height * (dpi / 25.4) ** 2 > 80_000_000:
        raise ValueError('Requested scan exceeds 80 megapixels; choose a smaller region or DPI')


@dataclass(frozen=True)
class PrintableArea:
    left: float
    top: float
    right: float
    bottom: float


def preflight_print(job, area):
    from app.services.layout import validate_layout
    problems = validate_layout(job)
    if problems:
        raise ValueError('\n'.join(problems[:10]))
    for placement in job.placements:
        if (placement.x < area.left - .05 or placement.y < area.top - .05 or
                placement.x + placement.width > area.right + .05 or
                placement.y + placement.height > area.bottom + .05):
            raise ValueError('A photo crosses this printer\'s printable boundary. Adjust the layout; no scaling was applied.')


def page_pixels(width_mm, height_mm, dpi=300):
    """Full physical paper raster, mapped back to the exact physical page rectangle."""
    size = (round(width_mm / 25.4 * dpi), round(height_mm / 25.4 * dpi))
    if min(size) <= 0 or size[0] * size[1] > 50_000_000:
        raise ValueError('Unsupported print raster size')
    return size


def preview_to_scanner(points,size,acquired_region):
    if len(points)!=4 or min(size)<=0:raise ValueError('Draw a nonempty scan rectangle')
    x,y,width,height=acquired_region
    xs=[p[0] for p in points];ys=[p[1] for p in points]
    if any(not math.isfinite(v) for v in xs+ys) or min(xs)<0 or min(ys)<0 or max(xs)>size[0] or max(ys)>size[1]:raise ValueError('Selection lies outside the acquired preview')
    result=[x+min(xs)/size[0]*width,y+min(ys)/size[1]*height,(max(xs)-min(xs))/size[0]*width,(max(ys)-min(ys))/size[1]*height]
    if min(result[2:])<1:raise ValueError('Choose a region at least 1 mm wide and high')
    return result


def direct_print_quality(job):
    """Use the actual rendered asset and pre-rotation cover scale, unlike legacy PA-009."""
    warnings=[]
    for photo in job.photos:
        for layer in photo.layers:
            if not layer.visible:continue
            with Image.open(layer.mask or layer.source) as image:
                width,height=image.size
                if image.getexif().get(274) in (5,6,7,8):width,height=height,width
            factor=min(1,6000/max(width,height))
            width=max(1,round(width*factor));height=max(1,round(height*factor))
            if not math.isfinite(layer.scale) or layer.scale<=0:raise ValueError('Invalid layer scale')
            effective=min(width/photo.width,height/photo.height)*25.4/layer.scale
            if effective<300:
                warnings.append(f'{photo.name}: approximately {effective:.0f} DPI from its rendered asset (300 recommended).')
    return warnings
