"""Groups transform ordinary layers; there is no second rendering hierarchy."""
import math


def transform_group(photo,index,x,y,scale,rotation):
    layer=photo.layers[index]
    if layer.locked:return
    if layer.group:
        ratio=scale/max(.001,layer.scale);angle=math.radians(-(rotation-layer.rotation));c,s=math.cos(angle),math.sin(angle)
        for member in photo.layers:
            if member is layer or member.group!=layer.group or member.locked:continue
            dx=(member.x-layer.x)*photo.width;dy=(member.y-layer.y)*photo.height
            member.x=x+(dx*c-dy*s)*ratio/photo.width;member.y=y+(dx*s+dy*c)*ratio/photo.height
            member.scale*=ratio;member.rotation+=rotation-layer.rotation
    layer.x=x;layer.y=y;layer.scale=scale;layer.rotation=rotation
