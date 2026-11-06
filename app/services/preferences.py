"""One set of defaults and validation for the active studio workflow."""
import math
from pathlib import Path
from PIL import ImageColor
from app.models.domain import Photo
from app.services.layout import geometry
from app.services.profiles import LAYOUTS


def default_preferences():
    return dict(default_workflow='dashboard',default_profile='Studio Portrait',joint_profile='Studio Joint Photo',
                output=str(Path.home()/'Documents'),portrait_width=45.,portrait_height=55.,
                joint_width=55.,joint_height=45.,background='#ADD8E6',quantity=4,border=True,
                border_color='#808080',border_mm=.2,landscape=False,margin=10.,gap_x=.2,gap_y=.2,
                layout='auto',rows=2,columns=2,dpi=300,processing_quality='balanced',
                automatic_framing='balanced',show_guides=True)


def validate_preferences(values):
    if values['default_workflow'] not in ('dashboard','cropper','portrait','joint'):raise ValueError('Choose a supported startup workflow.')
    for key in ('background','border_color'):ImageColor.getrgb(values[key])
    for mode in ('portrait','joint'):
        width,height=values[mode+'_width'],values[mode+'_height']
        if not all(math.isfinite(v) and 5<=v<=1000 for v in (width,height)):raise ValueError('Photo dimensions must be between 5 and 1000 mm.')
        if (mode=='portrait' and width>height) or (mode=='joint' and width<height):
            raise ValueError('Use portrait dimensions for individuals and landscape dimensions for joint photos.')
        Photo(width=width,height=height,quantity=values['quantity'],border_mm=values['border_mm']).validate()
    geometry(values)
    if values['layout'] not in LAYOUTS:raise ValueError('Choose a supported print layout.')
    if not 72<=values['dpi']<=600:raise ValueError('Render DPI must be between 72 and 600.')
    if values['processing_quality'] not in ('fast','balanced','fine'):raise ValueError('Choose a supported processing quality.')
    if values['automatic_framing'] not in ('auto','fit','fill','balanced','document','custom'):raise ValueError('Choose a supported framing mode.')
    if not values['output'].strip():raise ValueError('Choose a default save folder.')
    return values
