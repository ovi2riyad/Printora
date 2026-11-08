"""Optional nondestructive image adjustments shared by preview and export."""
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFilter

from app.models.domain import PROCESSING_LIMITS as LIMITS,validate_layer_processing as validate_processing


def skin_mask(rgb, faces):
    """Conservative face-only mask; eyes, brows, nose and mouth stay sharp."""
    mask=Image.new('L',rgb.size)
    draw=ImageDraw.Draw(mask);protected=Image.new('L',rgb.size,255);protect=ImageDraw.Draw(protected)
    for x,y,w,h in faces:
        draw.ellipse((x+.1*w,y+.1*h,x+.9*w,y+.94*h),fill=255)
        draw.rectangle((x,y+.2*h,x+w,y+.52*h),fill=0)
        draw.rectangle((x+.34*w,y+.42*h,x+.66*w,y+.72*h),fill=0)
        draw.rectangle((x+.2*w,y+.66*h,x+.8*w,y+.9*h),fill=0)
        for rectangle in [(x,y+.2*h,x+w,y+.52*h),(x+.34*w,y+.42*h,x+.66*w,y+.72*h),(x+.2*w,y+.66*h,x+.8*w,y+.9*h)]:protect.rectangle(rectangle,fill=0)
    if not faces:return mask
    feather=max(1,min(w for _,_,w,_ in faces)*.025)
    mask=np.asarray(mask.filter(ImageFilter.GaussianBlur(feather)),dtype=np.float32)/255
    pixels=np.asarray(rgb);ycrcb=cv2.cvtColor(pixels,cv2.COLOR_RGB2YCrCb)
    # Broad chroma gate supports a range of complexions, but never extends outside a face.
    skin=(ycrcb[:,:,1]>128)&(ycrcb[:,:,1]<185)&(ycrcb[:,:,2]>72)&(ycrcb[:,:,2]<140)
    return Image.fromarray(np.round(mask*skin*np.asarray(protected)).astype(np.uint8))


def process_portrait(rgb, layer):
    validate_processing(layer)
    if not any(getattr(layer,key,0) for key in LIMITS):return rgb
    pixels=np.asarray(rgb).copy()
    if layer.denoise:
        smooth=cv2.bilateralFilter(pixels,5,12+36*layer.denoise,3)
        pixels=cv2.addWeighted(pixels,1-layer.denoise,smooth,layer.denoise,0)
    if layer.skin_soften:
        from app.services.framing import detect_faces
        image=Image.fromarray(pixels);faces=detect_faces(image)
        for x,y,w,h in faces:
            left,top=max(0,int(x)),max(0,int(y));right,bottom=min(rgb.width,int(x+w+1)),min(rgb.height,int(y+h+1))
            if right<=left or bottom<=top:continue
            face=pixels[top:bottom,left:right].copy();fh,fw=face.shape[:2]
            mask=np.asarray(skin_mask(Image.fromarray(face),[(0,0,fw,fh)]),dtype=np.float32)[:,:,None]/255*layer.skin_soften*.75
            smooth=cv2.bilateralFilter(face,7,38,7)
            pixels[top:bottom,left:right]=np.clip(face*(1-mask)+smooth*mask,0,255).astype(np.uint8)
    if layer.shadows or layer.temperature:
        for start in range(0,rgb.height,128):
            value=pixels[start:start+128].astype(np.float32)/255
            if layer.shadows:
                luminance=value.mean(axis=2,keepdims=True)
                value+=layer.shadows*.35*(1-luminance)**2
            if layer.temperature:
                value[:,:,0]+=layer.temperature*.08;value[:,:,2]-=layer.temperature*.08
            pixels[start:start+128]=np.round(np.clip(value,0,1)*255).astype(np.uint8)
    return Image.fromarray(pixels)
