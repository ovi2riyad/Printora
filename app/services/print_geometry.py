"""Sheet-only rotation of a finished composition; editor pixels/sizes are untouched."""
from PIL import Image

ROTATIONS={'auto':'Automatic','none':'No rotation','cw':'90° clockwise','ccw':'90° counterclockwise','half':'180°'}

def print_rotation(photo,settings):
    if type(settings.get('auto_rotate_joint',False)) is not bool:raise ValueError('Automatic joint rotation must be a boolean')
    mode=photo.print_rotation
    if mode not in ROTATIONS:raise ValueError('Unsupported print rotation')
    if mode!='auto':return {'none':0,'cw':90,'ccw':270,'half':180}[mode]
    return 90 if settings.get('auto_rotate_joint',False) and not settings.get('landscape',False) and settings.get('policy')!='document' and 'joint' in photo.kind.lower() and photo.width>photo.height else 0

def footprint(photo,settings):
    angle=print_rotation(photo,settings)
    return (photo.height,photo.width,angle) if angle in (90,270) else (photo.width,photo.height,angle)

def rotated_image(image,angle):
    if type(angle) is not int or angle not in (0,90,180,270):raise ValueError('Invalid placement rotation')
    return image if angle==0 else image.transpose({90:Image.Transpose.ROTATE_270,180:Image.Transpose.ROTATE_180,270:Image.Transpose.ROTATE_90}[angle])
