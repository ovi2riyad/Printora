"""Validated, backward-compatible profile payloads; no government compliance claims."""
import copy
import math
import uuid
from PIL import ImageColor

REGIONS = ('Malaysia', 'India', 'USA', 'UK', 'Bangladesh', 'Custom')
LAYOUTS = {'auto': 'Automatic layout', 'grid_2x2': '2 columns × 2 rows',
           'custom': 'Custom rows and columns', 'max_fit': 'Maximum-fit layout'}


def normalize_profile(payload,validate=True):
    p = copy.deepcopy(payload)
    p['name'] = str(p.get('name', '')).strip()
    p['width'], p['height'] = float(p.get('width', 45)), float(p.get('height', 55))
    p.setdefault('kind', 'Joint' if 'joint' in p['name'].lower() or p['width'] > p['height'] else 'Individual')
    p['country'] = p.get('country') or 'Custom'
    p.setdefault('document_type', 'Studio joint' if p['kind'] == 'Joint' else 'Studio portrait')
    p['orientation'] = 'Landscape' if p['width'] > p['height'] else 'Portrait' if p['height'] > p['width'] else 'Square'
    for key, value in dict(quantity=4, background='#ADD8E6', border=True,
                           border_color='#808080', border_mm=.2, layout='auto',
                           rows=2, columns=2, notes='', url='', verification='Verify requirements').items():
        p.setdefault(key, value)
    for key,value in dict(recipe_id=uuid.uuid5(uuid.NAMESPACE_URL,'studio-recipe:'+p['name']).hex,recipe_version=1,paper_orientation='portrait',margin=10.,gap_x=.2,gap_y=.2).items():p.setdefault(key,value)
    if not validate:return p
    if not p['name'] or not all(math.isfinite(v) and 0 < v <= 1000 for v in (p['width'], p['height'])):
        raise ValueError('Enter a profile name and dimensions between 0 and 1000 mm.')
    if p['kind'] not in ('Individual', 'Joint'):
        raise ValueError('Choose Individual or Joint for the photo category.')
    if p['kind'] == 'Joint' and p['width'] < p['height']:
        raise ValueError('Joint profiles must be landscape: width must be at least height.')
    if p['kind'] == 'Individual' and p['width'] > p['height']:
        raise ValueError('Individual profiles must be portrait or square: height must be at least width.')
    if int(p['quantity']) != p['quantity'] or not 1 <= p['quantity'] <= 10000:
        raise ValueError('Profile quantity must be an integer between 1 and 10000.')
    p['quantity'] = int(p['quantity'])
    if not math.isfinite(float(p['border_mm'])) or not 0 <= p['border_mm'] < min(p['width'], p['height']) / 2:
        raise ValueError('Border must fit inside the photograph.')
    for key in ('background', 'border_color'):ImageColor.getrgb(p[key])
    if p['layout'] not in LAYOUTS:raise ValueError('Choose a supported default print layout.')
    if p['paper_orientation'] not in ('portrait','landscape','auto'):raise ValueError('Choose portrait, landscape or automatic paper orientation.')
    try:p['recipe_id']=uuid.UUID(str(p['recipe_id'])).hex
    except (ValueError,TypeError,AttributeError):raise ValueError('Recipe ID must be a UUID.')
    for key in ('margin','gap_x','gap_y'):
        p[key]=float(p[key])
        if not math.isfinite(p[key]) or not 0<=p[key]<=80:raise ValueError('Recipe margins/gaps must be between 0 and 80 mm.')
    for key in ('rows', 'columns'):
        if int(p[key]) != p[key] or not 1 <= p[key] <= 100:
            raise ValueError('Rows and columns must be integers between 1 and 100.')
    return p


def apply_profile(photo, profile, settings):
    """Apply print/canvas defaults without replacing layers, masks, or transforms."""
    p = normalize_profile(profile)
    for key in ('width', 'height', 'quantity', 'background', 'border', 'border_color', 'border_mm'):
        setattr(photo, key, p[key])
    photo.profile = p['name']
    settings.update(layout=p['layout'], rows=p['rows'], columns=p['columns'])
    settings.update(margin=p['margin'],gap_x=p['gap_x'],gap_y=p['gap_y'],auto_orientation=p['paper_orientation']=='auto')
    if p['paper_orientation']!='auto':settings['landscape']=p['paper_orientation']=='landscape'
    photo.provenance['recipe_snapshot']=copy.deepcopy(p)
    return photo
