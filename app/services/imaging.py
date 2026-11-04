from pathlib import Path
from functools import lru_cache
import hashlib
import threading
import sys
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

def remove_background(source,model_dir,cache_dir,force=False):
    global _session
    model=find_background_model(model_dir)
    stamp=f'{Path(source).resolve()}:{Path(source).stat().st_mtime_ns}:{model.resolve()}:{model.stat().st_mtime_ns}'
    target=Path(cache_dir)/(hashlib.sha256(stamp.encode()).hexdigest()+'.png')
    if target.exists() and not force: return str(target)
    with _lock:
        import numpy as np
        import onnxruntime as ort
        session_key=(str(model.resolve()),model.stat().st_mtime_ns)
        if _session is None or _session[0]!=session_key:
            options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
            _session=(session_key,ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider']))
        result=load_image(source,4000)
        sample=np.asarray(result.convert('RGB').resize((320,320),Image.Resampling.LANCZOS),dtype=np.float32)
        sample/=max(float(sample.max()),1e-6)
        sample=(sample-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
        tensor=np.ascontiguousarray(sample.transpose(2,0,1)[None],dtype=np.float32)
        prediction=_session[1].run(None,{_session[1].get_inputs()[0].name:tensor})[0][0,0]
        low,high=float(prediction.min()),float(prediction.max())
        normalized=(prediction-low)/(high-low) if high-low>1e-8 else np.clip(prediction,0,1)
        alpha=Image.fromarray(np.round(normalized*255).astype(np.uint8)).resize(result.size,Image.Resampling.LANCZOS)
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
        for stroke in layer.mask_strokes:
            points=[(round(x*im.width),round(y*im.height)) for x,y in stroke['points']]
            if not points:continue
            radius=max(1,round(stroke['radius']*im.width));paint=Image.new('L',im.size);draw=ImageDraw.Draw(paint)
            draw.line(points,fill=255,width=radius*2)
            for x,y in (points[0],points[-1]):draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=255)
            paint=paint.filter(ImageFilter.GaussianBlur(max(.3,radius*.15)))
            if stroke['mode']=='restore':
                if original_alpha is None:original_alpha=load_image(layer.source,limit).getchannel('A').resize(im.size)
                alpha=Image.composite(original_alpha,alpha,paint)
            else:alpha=Image.composite(Image.new('L',im.size,0),alpha,paint)
        rgb=im.convert('RGB')
        for field,enhancer in [('brightness',ImageEnhance.Brightness),('contrast',ImageEnhance.Contrast),('saturation',ImageEnhance.Color),('sharpness',ImageEnhance.Sharpness)]:
            value=getattr(layer,field)
            if value!=1:rgb=enhancer(rgb).enhance(value)
        im=rgb.convert('RGBA');im.putalpha(alpha)
    if layer.flip_h:im=ImageOps.mirror(im)
    if layer.flip_v:im=ImageOps.flip(im)
    return im

def render_photo(photo,dpi=300,before=False):
    photo.validate()
    size=(max(1,round(photo.width/25.4*dpi)),max(1,round(photo.height/25.4*dpi)))
    canvas=Image.new('RGBA',size,photo.background)
    for layer in photo.layers:
        if not layer.visible:continue
        im=prepare_layer(layer,before)
        fit=max(size[0]/im.width,size[1]/im.height)*layer.scale
        if layer.rotation:im=im.rotate(layer.rotation,Image.Resampling.BICUBIC,expand=True)
        im=im.resize((max(1,round(im.width*fit)),max(1,round(im.height*fit))),Image.Resampling.LANCZOS)
        canvas.alpha_composite(im,(round(layer.x*size[0]-im.width/2),round(layer.y*size[1]-im.height/2)))
    return canvas.convert('RGB')

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
    warnings=[]
    for l in photo.layers:
        with Image.open(l.source) as im:
            w,h=ImageOps.exif_transpose(im).size
        effective=min(w/photo.width,h/photo.height)*25.4/max(l.scale,0.01)
        if effective<300: warnings.append(f'{photo.name}: estimated {effective:.0f} DPI (300 recommended).')
    return warnings
