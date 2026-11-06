"""Canvas framing for a portrait, separate joint subjects or one combined photograph."""
import math
from PIL import ImageOps
from app.services.imaging import prepare_layer

def detect_faces(image):
    import cv2
    import numpy as np
    im=image.convert('RGB').copy();im.thumbnail((1400,1400));gray=cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2GRAY)
    classifier=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    faces=classifier.detectMultiScale(gray,1.08,5,minSize=(25,25));sx=image.width/im.width;sy=image.height/im.height
    return [(x*sx,y*sy,w*sx,h*sy) for x,y,w,h in faces]

def frame_photo(photo,mode='auto'):
    if mode in ('balanced','document','custom'):return compose_photo(photo,mode)
    layers=[l for l in photo.layers if l.visible];W,H=photo.width,photo.height
    for index,layer in enumerate(layers):
        if layer.locked:continue
        image=prepare_layer(layer,limit=2000);w,h=image.size;base=max(W/w,H/h)
        bbox=image.getchannel('A').point(lambda v:255 if v>35 else 0).getbbox() or (0,0,w,h)
        left,top,right,bottom=bbox;fw,fh=right-left,bottom-top
        faces=detect_faces(image) if mode=='auto' else []
        combined=len(layers)==1 and (photo.kind!='Individual' or len(faces)>1)
        if mode=='fill':factor=max(W/w,H/h);cx,cy=w/2,h/2;tx,ty=W/2,H/2
        elif mode=='fit':factor=min(W/w,H/h);cx,cy=w/2,h/2;tx,ty=W/2,H/2
        elif combined:
            # Preserve all heads as a group; place shoulders at the bottom edge.
            factor=min(W*.98/fw,H*.98/fh);cx=(left+right)/2;cy=bottom;tx,ty=W/2,H*.99
        else:
            factor=H*.98/max(1,fh);cx=(left+right)/2;cy=bottom;ty=H*1.01
            tx=W/2 if len(layers)==1 else W*(index+.5)/len(layers)
            if faces:
                x,y,face_w,face_h=max(faces,key=lambda r:r[2]*r[3]);cx=x+face_w/2
                # Fill down to the lower canvas edge; long mobile portraits get a head-and-shoulders crop.
                factor=max(factor,H*.36/face_h)
                head_y=ty-(bottom-top)*factor
                if head_y<.025*H:
                    ty=.025*H+(bottom-top)*factor
                # Keep a wide head visible even if shoulders extend past its half of a joint canvas.
                slot=W if len(layers)==1 else W/len(layers)
                factor=min(factor,slot*.82/max(1,face_w))
                ty=max(H*1.01,.035*H+(bottom-top)*factor)
        layer.rotation=0;layer.scale=factor/base
        layer.x=(tx-(cx-w/2)*factor)/W;layer.y=(ty-(cy-h/2)*factor)/H
    return photo


def compose_photo(photo, mode='balanced'):
    """Fit foreground into a physical safe rectangle; never force bottom contact."""
    settings=photo.composition
    W,H=photo.width,photo.height
    top,bottom,left,right=[float(settings.get(k,2)) for k in ('top','bottom','left','right')]
    if min(top,bottom,left,right)<0 or top+bottom>=H or left+right>=W:
        raise ValueError('Composition margins must leave space inside the photo.')
    if mode=='custom':return photo
    layers=[l for l in photo.layers if l.visible]
    for index,layer in enumerate(layers):
        if layer.locked:continue
        image=prepare_layer(layer,limit=2000);w,h=image.size
        l,t,r,b=image.getchannel('A').point(lambda a:255 if a>35 else 0).getbbox() or (0,0,w,h)
        slot=(W-left-right)/max(1,len(layers));available_h=H-top-bottom
        factor=min(slot/max(1,r-l),available_h/max(1,b-t))*float(settings.get('subject_scale',1))
        ax=float(settings.get('horizontal',.5));ay=float(settings.get('vertical',.5))
        tx=left+index*slot+(slot-(r-l)*factor)*ax
        ty=top+(available_h-(b-t)*factor)*ay
        if mode=='document':
            faces=detect_faces(image)
            if faces:
                fx,fy,fw,fh=max(faces,key=lambda box:box[2]*box[3])
                desired=float(settings.get('head_position',.28))*H
                ty=max(top,min(H-bottom-(b-t)*factor,desired-(fy+fh/2-t)*factor))
        if settings.get('shoulder_position') is not None:
            ty=max(top,min(H-bottom-(b-t)*factor,float(settings['shoulder_position'])*H-(b-t)*factor))
        layer.rotation=0;layer.scale=factor/max(W/w,H/h)
        layer.x=(tx+(w/2-l)*factor)/W;layer.y=(ty+(h/2-t)*factor)/H
    settings['mode']=mode
    return photo

def align_layers(photo,action):
    active=[l for l in photo.layers if l.visible and not l.locked]
    if not active:return photo
    if action in ('vertical_center','safe_top','safe_bottom'):
        top=photo.composition.get('top',2);bottom=photo.composition.get('bottom',2)
        for layer in active:
            im=prepare_layer(layer,limit=1600);factor=max(photo.width/im.width,photo.height/im.height)*layer.scale
            if layer.rotation:im=im.rotate(layer.rotation,expand=True)
            box=im.getchannel('A').getbbox() or (0,0,*im.size)
            anchor=box[1] if action=='safe_top' else box[3] if action=='safe_bottom' else (box[1]+box[3])/2
            target=top if action=='safe_top' else photo.height-bottom if action=='safe_bottom' else (top+photo.height-bottom)/2
            layer.y=(target-(anchor-im.height/2)*factor)/photo.height
        return photo
    if action=='center':
        bounds=[]
        for l in active:
            im=prepare_layer(l,limit=1600);factor=max(photo.width/im.width,photo.height/im.height)*l.scale
            if l.rotation:im=im.rotate(l.rotation,expand=True)
            box=im.getchannel('A').getbbox() or (0,0,*im.size)
            bounds.append((l.x*photo.width+(box[0]-im.width/2)*factor,l.x*photo.width+(box[2]-im.width/2)*factor))
        delta=(photo.width/2-(min(a for a,_ in bounds)+max(b for _,b in bounds))/2)/photo.width
        for l in active:l.x+=delta
    elif action=='bottom':
        for l in active:
            im=prepare_layer(l,limit=1600);factor=max(photo.width/im.width,photo.height/im.height)*l.scale
            bbox=im.getchannel('A').getbbox() or (0,0,*im.size);l.y=(photo.height*1.01-(bbox[3]-im.height/2)*factor)/photo.height
    elif action=='match':
        measurements=[]
        for l in active:
            im=prepare_layer(l,limit=1600);faces=detect_faces(im)
            if faces:
                h=max(faces,key=lambda r:r[2]*r[3])[3];base=max(photo.width/im.width,photo.height/im.height);measurements.append((l,h*base*l.scale))
        if measurements:
            target=sum(h for _,h in measurements)/len(measurements)
            for l,h in measurements:l.scale*=target/h
        align_layers(photo,'bottom')
    return photo
