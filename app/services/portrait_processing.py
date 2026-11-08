"""Nondestructive, CPU-only retouching shared by preview and final rendering."""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from app.models.domain import PROCESSING_LIMITS as LIMITS, validate_layer_processing as validate_processing

TONE_DEFAULTS=dict(brightness=1.,contrast=1.,saturation=1.,sharpness=1.)


def portrait_faces(rgb):
    from app.services.framing import detect_faces
    faces=detect_faces(rgb)
    if not faces:
        # A second luminance-only detection pass helps faded/low-contrast scans.
        gray=cv2.cvtColor(np.asarray(rgb),cv2.COLOR_RGB2GRAY)
        enhanced=cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8)).apply(gray)
        faces=detect_faces(Image.fromarray(enhanced).convert('RGB'))
    return faces


def skin_mask(rgb,faces):
    """Feather face/skin coverage while protecting facial features exactly."""
    mask=Image.new('L',rgb.size);draw=ImageDraw.Draw(mask)
    protected=Image.new('L',rgb.size,255);protect=ImageDraw.Draw(protected)
    for x,y,w,h in faces:
        draw.ellipse((x+.04*w,y+.02*h,x+.96*w,y+.98*h),fill=255)
        for rect in [(x+.1*w,y+.2*h,x+.9*w,y+.50*h),
                     (x+.36*w,y+.44*h,x+.64*w,y+.72*h),
                     (x+.22*w,y+.7*h,x+.78*w,y+.91*h)]:
            protect.rectangle(rect,fill=0)
    if not faces:return mask
    feather=max(.7,min(w for _,_,w,_ in faces)*.018)
    coverage=np.asarray(mask.filter(ImageFilter.GaussianBlur(feather)),np.float32)/255
    chroma=cv2.cvtColor(np.asarray(rgb),cv2.COLOR_RGB2YCrCb)
    skin=(chroma[:,:,1]>125)&(chroma[:,:,1]<190)&(chroma[:,:,2]>65)&(chroma[:,:,2]<148)&(chroma[:,:,0]>20)&(chroma[:,:,0]<248)
    skin=cv2.GaussianBlur(skin.astype(np.float32),(0,0),max(.6,feather*.5))
    return Image.fromarray(np.round(coverage*skin*np.asarray(protected)).astype(np.uint8))


def noise_level(channel,mask=None):
    """Robust high-frequency estimate from relatively flat areas, not hard edges."""
    value=channel.astype(np.float32)
    residual=value-cv2.GaussianBlur(value,(0,0),1.)
    gradient=np.abs(cv2.Sobel(value,cv2.CV_32F,1,0))+np.abs(cv2.Sobel(value,cv2.CV_32F,0,1))
    valid=np.ones(channel.shape,bool) if mask is None else mask.astype(bool).copy()
    if not np.any(valid):return 0.
    valid &= gradient<=np.percentile(gradient[valid],60)
    samples=residual[valid]
    return float(np.median(np.abs(samples-np.median(samples)))*1.4826) if samples.size else 0.


def _denoise_channel(channel,strength):
    # Overlapped tiles bound temporary buffers and avoid seams on camera images.
    if not strength:return channel
    result=np.empty_like(channel);border=14
    for top in range(0,channel.shape[0],256):
        bottom=min(top+256,channel.shape[0]);start=max(0,top-border);end=min(channel.shape[0],bottom+border)
        tile=np.ascontiguousarray(channel[start:end])
        filtered=cv2.fastNlMeansDenoising(tile,None,2+20*strength,7,21)
        result[top:bottom]=filtered[top-start:bottom-start]
    return result


def process_portrait(rgb,layer):
    validate_processing(layer)
    if not any(getattr(layer,key,0) for key in LIMITS):return rgb
    pixels=np.asarray(rgb).copy()
    if layer.denoise or layer.color_denoise:
        lab=cv2.cvtColor(pixels,cv2.COLOR_RGB2LAB)
        if layer.denoise:lab[:,:,0]=_denoise_channel(lab[:,:,0],layer.denoise)
        if layer.color_denoise:
            for channel in (1,2):lab[:,:,channel]=_denoise_channel(lab[:,:,channel],layer.color_denoise)
        pixels=cv2.cvtColor(lab,cv2.COLOR_LAB2RGB)
    if layer.skin_soften:
        for x,y,w,h in portrait_faces(Image.fromarray(pixels)):
            left,top=max(0,int(x)),max(0,int(y));right,bottom=min(rgb.width,int(x+w)),min(rgb.height,int(y+h))
            if right<=left or bottom<=top:continue
            face=pixels[top:bottom,left:right].copy();fh,fw=face.shape[:2]
            mask=np.asarray(skin_mask(Image.fromarray(face),[(0,0,fw,fh)]),np.float32)[:,:,None]/255*layer.skin_soften
            smooth=cv2.bilateralFilter(face,9,45,7).astype(np.float32)
            smooth=cv2.GaussianBlur(smooth,(0,0),max(.6,fw*.008))
            detail=face.astype(np.float32)-cv2.GaussianBlur(face.astype(np.float32),(0,0),max(.6,fw*.004))
            softened=np.clip(smooth+.18*detail,0,255)
            pixels[top:bottom,left:right]=np.round(face*(1-mask)+softened*mask).astype(np.uint8)
    if layer.shadows or layer.temperature or layer.tint:
        for start in range(0,rgb.height,128):
            value=pixels[start:start+128].astype(np.float32)/255
            if layer.shadows:
                luminance=value.mean(axis=2,keepdims=True)
                value+=layer.shadows*.35*(1-luminance)**2
            # Multiplicative balance retains black, unlike the old additive warmth.
            value[:,:,0]*=2**(.3*layer.temperature+.12*layer.tint)
            value[:,:,1]*=2**(-.24*layer.tint)
            value[:,:,2]*=2**(-.3*layer.temperature+.12*layer.tint)
            pixels[start:start+128]=np.round(np.clip(value,0,1)*255).astype(np.uint8)
    return Image.fromarray(pixels)


def auto_adjustments(image):
    """Analyze unedited pixels; return repeatable, restrained settings, never edits."""
    sample=image.convert('RGBA');sample.thumbnail((800,800))
    rgb=sample.convert('RGB');pixels=np.asarray(rgb);alpha=np.asarray(sample.getchannel('A'))
    valid=alpha>200
    result={**TONE_DEFAULTS,**{key:0. for key in LIMITS}}
    if np.count_nonzero(valid)<64:return result,False
    faces=portrait_faces(rgb);gray=cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
    metering=valid.copy()
    if faces:
        face_area=np.zeros(valid.shape,np.uint8)
        for x,y,w,h in faces:
            cv2.ellipse(face_area,(int(x+w/2),int(y+h/2)),(max(1,int(w*.35)),max(1,int(h*.4))),0,0,360,1,-1)
        if np.count_nonzero(face_area&valid)>64:metering &= face_area.astype(bool)
    values=gray[metering];middle=float(np.median(values));high=float(np.percentile(gray[valid],98))
    target=145 if faces else 125
    result['brightness']=float(np.clip(target/max(middle,1),.92,1.4))
    if high>245:result['brightness']=min(1.03,result['brightness'])
    spread=float(np.percentile(values,90)-np.percentile(values,10))
    result['contrast']=1.1 if spread<70 else 1.
    result['shadows']=float(np.clip((105-middle)/180,0,.35))
    hsv=cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV)
    saturation=float(np.median(hsv[:,:,1][valid]))/255
    result['saturation']=.9 if saturation>.65 else 1.04 if .1<saturation<.3 else 1.
    # White balance only from near-neutral midtones, never from skin alone.
    neutral=valid&(hsv[:,:,1]<(24 if faces else 45))&(gray>(150 if faces else 40))&(gray<250)
    if faces:
        # Pale skin can have low saturation. Never use a face as a gray card.
        for x,y,w,h in faces:
            left,top=max(0,int(x-.2*w)),max(0,int(y-.2*h));right,bottom=min(rgb.width,int(x+1.2*w)),min(rgb.height,int(y+1.2*h))
            neutral[top:bottom,left:right]=False
    if np.count_nonzero(neutral)>max(64,np.count_nonzero(valid)*.03):
        channels=np.median(pixels[neutral],axis=0).astype(float)+1
        result['temperature']=float(np.clip(np.log2(channels[2]/channels[0])/.6,-.5,.5))
        result['tint']=float(np.clip(np.log2(channels[1]/np.sqrt(channels[0]*channels[2]))/.36,-.5,.5))
    lab=cv2.cvtColor(pixels,cv2.COLOR_RGB2LAB)
    noise=noise_level(lab[:,:,0],metering);color_noise=max(noise_level(lab[:,:,1],metering),noise_level(lab[:,:,2],metering))
    result['denoise']=float(np.clip((noise-1)/14,0,.85))
    result['color_denoise']=float(np.clip((color_noise-1)/14,0,.9))
    result['sharpness']=1.15 if noise<6 else 1.08
    result['skin_soften']=.38 if faces else 0.
    return {key:round(value,2) for key,value in result.items()},bool(faces)
