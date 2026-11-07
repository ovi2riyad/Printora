"""Validation of optional config values; never rewrites stored evidence."""
import math
from PIL import ImageColor
from app.services.preferences import default_preferences
from app.services.hardware import HARDWARE_DEFAULTS,validate_hardware_setting


OPTIONAL_DEFAULTS = dict(default_preferences(), recent_colors=[], recipe_usage={},
    composition_presets={}, calibrations={}, printer_profiles={}, model_dir=None,
    printer_name='Default printer', theme='Dark', paper='A4',panel_layout={},workflow_defaults={})
OPTIONAL_DEFAULTS.update(HARDWARE_DEFAULTS)
ENUMS = dict(default_workflow=('dashboard','cropper','portrait','joint'),
    layout=('auto','grid_2x2','custom','max_fit'), processing_quality=('fast','balanced','fine'),
    automatic_framing=('auto','fit','fill','balanced','document','custom'),
    theme=('Dark','Light','System'), paper=('A4',))
RANGES = dict(quantity=(1,10000), dpi=(72,600), rows=(1,100), columns=(1,100),
    margin=(0,104), gap_x=(0,1000), gap_y=(0,1000), border_mm=(0,1000),
    portrait_width=(5,1000),portrait_height=(5,1000),joint_width=(5,1000),joint_height=(5,1000))


def number(value, low, high):
    return type(value) in (int,float) and math.isfinite(value) and low <= value <= high


def color(value):
    if not isinstance(value,str):return False
    try:ImageColor.getrgb(value);return True
    except (ValueError,TypeError):return False


def framing(value):
    if not isinstance(value,dict):return False
    limits=dict(top=(0,100),bottom=(0,100),left=(0,100),right=(0,100),
                subject_scale=(.1,3),head_position=(0,1),horizontal=(0,1),vertical=(0,1),shoulder_position=(0,1))
    return all((v in ('balanced','document','custom') if k=='mode' and isinstance(v,str)
                else number(v,*limits[k]) if k in limits else False) for k,v in value.items())


def validate_optional(key, value):
    """Return (usable value, recovery reason); reject only the affected option/entry."""
    if key=='workflow_defaults':
        from app.services.workflow_preferences import validate_defaults
        return validate_defaults(value)
    if key=='panel_layout':
        if not isinstance(value,dict) or len(value)>40:raise ValueError('expected panel layout object')
        valid={k:v for k,v in value.items() if isinstance(k,str) and len(k)<=80 and isinstance(v,dict) and v.get('mode') in ('large','small','icons') and type(v.get('width')) is int and number(v.get('width'),48,800)}
        return valid,'invalid panel entries ignored' if len(valid)!=len(value) else None
    if key in ('input_folder','scans_folder','backups_folder'):
        from pathlib import Path
        if not isinstance(value,str) or not value.strip() or '\x00' in value or not Path(value).expanduser().is_absolute():raise ValueError('expected an absolute working folder')
        return value,None
    if key in HARDWARE_DEFAULTS:
        return validate_hardware_setting(key,value),None
    if key == 'recent_colors':
        if not isinstance(value,list):raise ValueError('expected a list of colors')
        valid=[v for v in value if color(v)]
        return valid, 'invalid color entries ignored' if len(valid)!=len(value) else None
    if key in ('recipe_usage','composition_presets','calibrations','printer_profiles'):
        if not isinstance(value,dict):raise ValueError('expected an object')
        def valid_entry(name,item):
            if not isinstance(name,str) or not name.strip():return False
            if key=='recipe_usage':return type(item) is int and item>=0
            if key=='calibrations':return number(item,0.000001,1000)
            if key=='composition_presets':return framing(item)
            return (isinstance(item,dict) and
                    all(k in item and number(item[k],50,150) for k in ('measured_width','measured_height')) and
                    all(k in item and number(item[k],.000001,1000) for k in ('driver_x','driver_y')))
        valid={k:v for k,v in value.items() if valid_entry(k,v)}
        return valid, 'invalid optional entries ignored' if len(valid)!=len(value) else None
    if key in ('background','border_color'):
        if not color(value):raise ValueError('expected a valid color')
    elif key in ENUMS:
        if not isinstance(value,str) or value not in ENUMS[key]:raise ValueError('unsupported option')
    elif key in RANGES:
        if not number(value,*RANGES[key]):raise ValueError('expected a finite number within the supported range')
        if key in ('quantity','dpi','rows','columns') and type(value) is not int:raise ValueError('expected a whole number')
    elif isinstance(OPTIONAL_DEFAULTS[key],bool):
        if type(value) is not bool:raise ValueError('expected a boolean')
    elif key=='model_dir' and value is None:pass
    elif not isinstance(value,str) or '\x00' in value:
        raise ValueError('expected text')
    elif key in ('output','printer_name') and not value.strip():raise ValueError('expected nonempty text')
    return value,None
