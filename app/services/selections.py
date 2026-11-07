"""Resolution-independent selections in unflipped image coordinates.

Only vector expressions are persisted in mask edits. UI selections are transient.
Budgets bound evaluation of imported jobs without allocating full camera rasters.
"""
import copy
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter

TOOLS = {'rectangle':'Rectangle', 'ellipse':'Ellipse', 'lasso':'Freehand lasso',
         'polygon':'Polygonal lasso', 'selection_brush':'Selection brush'}

def combine(current, shape, mode='new'):
    if mode not in ('new','add','subtract','intersect'):raise ValueError('Unknown selection operation')
    if mode=='new' or current is None and mode=='add':return copy.deepcopy(shape)
    return {'kind':mode,'left':copy.deepcopy(current or {'kind':'empty'}),'right':copy.deepcopy(shape)}

def selection_mask(expression, size):
    w,h=map(int,size)
    if min(w,h)<1 or w*h>50_000_000:raise ValueError('Selection raster is too large')
    def complexity(node,depth=1):
        if not isinstance(node,dict) or depth>32:raise ValueError('Selection expression is too complex')
        children=[node[key] for key in ('left','right','selection') if key in node]
        count,maximum=1,depth
        for child in children:
            n,d=complexity(child,depth+1);count+=n;maximum=max(maximum,d)
            if count>256:raise ValueError('Selection expression is too complex')
        return count,maximum
    nodes,depth=complexity(expression)
    if w*h*nodes>800_000_000 or w*h*depth>250_000_000:raise ValueError('Selection is too complex at this image resolution; simplify it before exporting')
    budget=[256]
    def number(value):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>100:raise ValueError('Invalid selection coordinate')
        return value
    def evaluate(node,depth=0):
        budget[0]-=1
        if budget[0]<0 or depth>32 or not isinstance(node,dict):raise ValueError('Selection expression is too complex')
        kind=node.get('kind');blank=lambda:Image.new('L',(w,h))
        if kind=='empty':return blank()
        if kind=='all':return Image.new('L',(w,h),255)
        if kind in ('add','subtract','intersect'):
            a,b=evaluate(node['left'],depth+1),evaluate(node['right'],depth+1)
            return {'add':ImageChops.lighter,'subtract':ImageChops.subtract,'intersect':ImageChops.darker}[kind](a,b)
        if kind in ('invert','feather','expand','contract'):
            a=evaluate(node['selection'],depth+1)
            if kind=='invert':return ImageChops.invert(a)
            radius=number(node.get('radius',0))*w
            if radius<0:raise ValueError('Negative selection radius')
            if kind=='feather':return a.filter(ImageFilter.GaussianBlur(min(radius,2048)))
            # cv2 morphology is bounded and substantially faster than large Pillow rank filters.
            import cv2
            import numpy as np
            r=min(2048,round(radius))
            if not r:return a
            kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*r+1,2*r+1))
            fn=cv2.dilate if kind=='expand' else cv2.erode
            return Image.fromarray(fn(np.asarray(a),kernel,borderType=cv2.BORDER_CONSTANT,borderValue=0))
        points=node.get('points',[])
        if not isinstance(points,list) or len(points)>8192:raise ValueError('Invalid selection points')
        xy=[]
        for point in points:
            if not isinstance(point,(list,tuple)) or len(point)!=2:raise ValueError('Invalid selection point')
            xy.append((round(number(point[0])*w),round(number(point[1])*h)))
        out=blank();draw=ImageDraw.Draw(out)
        if kind in ('rectangle','ellipse'):
            if len(xy)!=2:raise ValueError('Selection needs two corners')
            a,b=xy;box=(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]))
            (draw.rectangle if kind=='rectangle' else draw.ellipse)(box,fill=255)
        elif kind in ('lasso','polygon'):
            if len(xy)>=3:draw.polygon(xy,fill=255)
        elif kind=='selection_brush':
            r=max(1,round(number(node.get('radius',.02))*w))
            if r>4096:raise ValueError('Selection brush is too large')
            if len(xy)>1:draw.line(xy,fill=255,width=2*r)
            for x,y in xy:draw.ellipse((x-r,y-r,x+r,y+r),fill=255)
        else:raise ValueError('Unknown selection shape')
        return out
    return evaluate(expression)

def apply_selection(alpha, baseline, edit):
    coverage=selection_mask(edit['selection'],alpha.size)
    target=baseline if edit.get('mode')=='restore_selection' else Image.new('L',alpha.size)
    return Image.composite(target,alpha,coverage)
