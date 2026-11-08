from pathlib import Path
from functools import lru_cache
import hashlib
import threading
import sys
import math
from PIL import Image, ImageOps, ImageFilter,ImageEnhance,ImageDraw

SUPPORTED={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'}
_lock=threading.Lock()
_session=None

def load_image(path,limit=6000):
    if not Path(path).exists(): raise FileNotFoundError(f'Missing source image: {path}. Restore the file or replace this layer.')
    with Image.open(path) as im:
        im.draft('RGB',(limit,limit))
        im=ImageOps.exif_transpose(im); im.thumbnail((limit,limit)); return im.convert('RGBA')

def import_info(path):
    if Path(path).suffix.lower() not in SUPPORTED: raise ValueError(f'Unsupported image: {Path(path).name}')
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        oriented=ImageOps.exif_transpose(im)
        return str(Path(path).resolve()),oriented.size,load_image(path,160)

def find_background_model(model_dir=None):
    """Find installed or packaged models without requiring internet at runtime."""
    from app.core.database import data_root
    folders=[]
    if model_dir and str(model_dir).strip():folders.append(Path(model_dir))
    folders.extend([data_root()/'models',Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'models'])
    for folder in folders:
        for name in ('u2net_human_seg.onnx','u2netp.onnx'):
            model=folder/name
            if model.is_file() and model.stat().st_size>1000000:return model
    raise ValueError('Background model not found. Open Settings to install the portrait model, or keep the models folder supplied with the application.')

def refine_alpha(image,alpha):
    """Small guided matte refinement, using source luminance to retain real edges."""
    import cv2
    import numpy as np
    guide=np.asarray(image.convert('L'),dtype=np.float32)/255
    matte=np.asarray(alpha,dtype=np.float32)/255
    mean=lambda value:cv2.boxFilter(value,-1,(7,7),borderType=cv2.BORDER_REFLECT)
    mi,mp=mean(guide),mean(matte)
    a=(mean(guide*matte)-mi*mp)/(mean(guide*guide)-mi*mi+.001)
    b=mp-a*mi
    result=np.clip(mean(a)*guide+mean(b),0,1)
    # Keep confident foreground/background unchanged; refine only uncertain edges.
    result=np.where((matte>.02)&(matte<.98),result,matte)
    return Image.fromarray(np.round(result*255).astype(np.uint8))


def reduce_halo(image,amount):
    """Optional edge-color cleanup using neighboring opaque foreground colors."""
    import cv2
    import numpy as np
    rgba=np.asarray(image,dtype=np.float32);alpha=rgba[:,:,3:4]/255
    core=(alpha>.95).astype(np.float32)
    weights=cv2.GaussianBlur(core,(0,0),3)
    if weights.ndim==2:weights=weights[:,:,None]
    colors=cv2.GaussianBlur(rgba[:,:,:3]*core,(0,0),3)/np.maximum(weights,.0001)
    blend=np.clip(float(amount),0,1)*(1-alpha)*((alpha>.02)&(alpha<.98)&(weights>.01))
    rgba[:,:,:3]=rgba[:,:,:3]*(1-blend)+colors*blend
    return Image.fromarray(np.clip(rgba,0,255).astype(np.uint8))


def remove_background(source,model_dir,cache_dir,force=False,quality='balanced'):
    global _session
    model=find_background_model(model_dir)
    if quality not in ('fast','balanced','fine'):raise ValueError('Choose fast, balanced, or fine processing quality.')
    stamp=f'{Path(source).resolve()}:{Path(source).stat().st_mtime_ns}:{model.resolve()}:{model.stat().st_mtime_ns}:{quality}'
    target=Path(cache_dir)/(hashlib.sha256(stamp.encode()).hexdigest()+'.png')
    if target.exists() and not force: return str(target)
    with _lock:
        import numpy as np
        import onnxruntime as ort
        session_key=(str(model.resolve()),model.stat().st_mtime_ns)
        if _session is None or _session[0]!=session_key:
            options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
            _session=(session_key,ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider']))
        result=load_image(source,2000 if quality=='fast' else 4000)
        sample=np.asarray(result.convert('RGB').resize((320,320),Image.Resampling.LANCZOS),dtype=np.float32)
        sample/=max(float(sample.max()),1e-6)
        sample=(sample-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
        tensor=np.ascontiguousarray(sample.transpose(2,0,1)[None],dtype=np.float32)
        prediction=_session[1].run(None,{_session[1].get_inputs()[0].name:tensor})[0][0,0]
        low,high=float(prediction.min()),float(prediction.max())
        normalized=(prediction-low)/(high-low) if high-low>1e-8 else np.clip(prediction,0,1)
        alpha=Image.fromarray(np.round(normalized*255).astype(np.uint8)).resize(result.size,Image.Resampling.LANCZOS)
        if quality=='fine':alpha=refine_alpha(result,alpha)
        from PIL import ImageChops
        result.putalpha(ImageChops.multiply(result.getchannel('A'),alpha))
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_suffix('.tmp'); result.save(tmp,format='PNG'); tmp.replace(target)
    return str(target)

def prepare_layer(layer,before=False,limit=6000):
    im=load_image(layer.source if before else layer.mask or layer.source,limit)
    if not before:
        alpha=im.getchannel('A')
        if layer.erosion:
            k=2*abs(layer.erosion)+1;alpha=alpha.filter(ImageFilter.MinFilter(k) if layer.erosion>0 else ImageFilter.MaxFilter(k))
        if layer.feather:alpha=alpha.filter(ImageFilter.GaussianBlur(layer.feather))
        original_alpha=None
        baseline_alpha=alpha.copy()
        for stroke in layer.mask_strokes:
            if stroke.get('kind')=='selection':
                from app.services.selections import apply_selection
                alpha=apply_selection(alpha,baseline_alpha,stroke);continue
            points=[(round(x*im.width),round(y*im.height)) for x,y in stroke['points']]
            if not points:continue
            radius=max(1,round(stroke['radius']*im.width));paint=Image.new('L',im.size);draw=ImageDraw.Draw(paint)
            draw.line(points,fill=255,width=radius*2,joint='curve')
            for x,y in (points[0],points[-1]):draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=255)
            hardness=stroke.get('hardness')
            blur=max(.3,radius*.15) if hardness is None else max(.3,radius*(1-max(0,min(1,float(hardness))))*.6)
            extra=float(stroke.get('feather',0))
            if not math.isfinite(extra) or not 0<=extra<=1:raise ValueError('Invalid brush feather')
            blur+=extra*im.width
            paint=paint.filter(ImageFilter.GaussianBlur(blur))
            opacity=max(0,min(1,float(stroke.get('opacity',1))))
            if opacity!=1:paint=paint.point(lambda v:round(v*opacity))
            if stroke.get('clip_selection'):
                from app.services.selections import selection_mask
                from PIL import ImageChops
                paint=ImageChops.multiply(paint,selection_mask(stroke['clip_selection'],im.size))
            if stroke['mode']=='restore':
                if original_alpha is None:original_alpha=load_image(layer.source,limit).getchannel('A').resize(im.size)
                alpha=Image.composite(original_alpha,alpha,paint)
            else:alpha=Image.composite(Image.new('L',im.size,0),alpha,paint)
        rgb=im.convert('RGB')
        from app.services.portrait_processing import process_portrait
        rgb=process_portrait(rgb,layer)
        for field,enhancer in [('brightness',ImageEnhance.Brightness),('contrast',ImageEnhance.Contrast),('saturation',ImageEnhance.Color),('sharpness',ImageEnhance.Sharpness)]:
            value=getattr(layer,field)
            if value!=1:rgb=enhancer(rgb).enhance(value)
        im=rgb.convert('RGBA');im.putalpha(alpha)
        if layer.defringe:im=reduce_halo(im,layer.defringe)
    if layer.flip_h:im=ImageOps.mirror(im)
    if layer.flip_v:im=ImageOps.flip(im)
    return im

def render_photo(photo,dpi=300,before=False):
    photo.validate()
    size=(max(1,round(photo.width/25.4*dpi)),max(1,round(photo.height/25.4*dpi)))
    if size[0]*size[1]>50_000_000:raise ValueError('The requested image exceeds 50 megapixels. Reduce its dimensions or render DPI before exporting.')
    canvas=Image.new('RGBA',size,photo.background)
    for layer in photo.layers:
        if not layer.visible:continue
        im=prepare_layer(layer,before)
        fit=max(size[0]/im.width,size[1]/im.height)*layer.scale
        if layer.rotation:im=im.rotate(layer.rotation,Image.Resampling.BICUBIC,expand=True)
        layer_size=(max(1,round(im.width*fit)),max(1,round(im.height*fit)))
        if layer_size[0]*layer_size[1]>100_000_000:raise ValueError('This layer is enlarged beyond the safe rendering limit. Reduce its zoom before exporting.')
        im=im.resize(layer_size,Image.Resampling.LANCZOS)
        canvas.alpha_composite(im,(round(layer.x*size[0]-im.width/2),round(layer.y*size[1]-im.height/2)))
    return canvas.convert('RGB')


def render_bordered_photo(photo,dpi=300):
    """Shared preview/image-export border; PDF uses the same inside geometry."""
    im=render_photo(photo,dpi)
    if photo.border and photo.border_mm:
        ImageDraw.Draw(im).rectangle((0,0,im.width-1,im.height-1),outline=photo.border_color,width=max(1,round(photo.border_mm/25.4*dpi)))
    return im


def export_photo_image(photo,path,dpi=300):
    import os
    import tempfile
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    if target.suffix.lower() not in ('.png','.jpg','.jpeg'):raise ValueError('Choose PNG or JPEG for the edited photograph.')
    fd,tmp=tempfile.mkstemp(suffix=target.suffix,dir=target.parent);os.close(fd)
    try:
        im=render_bordered_photo(photo,dpi)
        im.save(tmp,dpi=(dpi,dpi),**({'quality':95} if target.suffix.lower() in ('.jpg','.jpeg') else {}))
        os.replace(tmp,target)
    finally:
        if Path(tmp).exists():Path(tmp).unlink()
    return str(target)

def face_position(layer,width,height):
    import cv2
    import numpy as np
    im=load_image(layer.source,1800)
    gray=cv2.cvtColor(np.array(im),cv2.COLOR_RGBA2GRAY)
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    faces=cascade.detectMultiScale(gray,1.1,5,minSize=(30,30))
    if len(faces)==0:raise ValueError('No frontal face found. Use manual scale and positioning.')
    x,y,w,h=max(faces,key=lambda r:r[2]*r[3])
    base=max(width/im.width,height/im.height)
    layer.scale=(height*0.32/h)/base
    layer.x=0.5-(x+w/2-im.width/2)*base*layer.scale/width
    layer.y=0.36-(y+h/2-im.height/2)*base*layer.scale/height
    return layer

def resolution_warnings(photo):
    from app.services.hardware import direct_print_quality
    from app.models.domain import Job
    return direct_print_quality(Job(photos=[photo]))
