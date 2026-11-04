"""Local sheet splitting, perspective crops and an in-memory prepared-photo tray."""
from dataclasses import dataclass,field
from pathlib import Path
import uuid
import math
import sqlite3
import threading
import hashlib
import shutil
import json
from PIL import Image

@dataclass
class CropRegion:
    points: list
    rotation: int = 0

@dataclass
class PreparedPhoto:
    name: str
    _image: Image.Image | None
    source: str = ''
    id: str = field(default_factory=lambda:uuid.uuid4().hex)
    asset: str = ''
    serial: int = 0
    thumb: str = ''
    dimensions: tuple = (0,0)

    @property
    def image(self):
        if self._image is not None:return self._image
        if not Path(self.asset).is_file():raise FileNotFoundError(f'Saved photo #{self.serial:06d} is missing. Restore its library file from backup or import it again.')
        with Image.open(self.asset) as image:return image.convert('RGBA')
    @property
    def display_name(self):return f'#{self.serial:06d} · {self.name}' if self.serial else self.name
    @property
    def size(self):return self._image.size if self._image is not None else self.dimensions
    def thumbnail(self,size=(100,120)):
        try:
            if self.thumb and Path(self.thumb).exists():
                with Image.open(self.thumb) as image:result=image.convert('RGB')
            else:result=self.image.copy()
        except (OSError,ValueError):
            from PIL import ImageDraw
            result=Image.new('RGB',size,'#dce3eb');ImageDraw.Draw(result).text((4,4),'Missing',fill='#7d4250')
        result.thumbnail(size);return result

class CropTray:
    def __init__(self,max_pixels=120_000_000,root=None):
        self.items=[];self.max_pixels=max_pixels;self.root=Path(root) if root else None;self.lock=threading.RLock();self.conn=None
        if self.root:
            self.root.mkdir(parents=True,exist_ok=True)
            self.conn=sqlite3.connect(self.root/'library.db',check_same_thread=False)
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.executescript('CREATE TABLE IF NOT EXISTS photos(serial INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,name TEXT,source TEXT,asset TEXT,thumb TEXT,width INTEGER,height INTEGER,deleted INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS sources(serial INTEGER PRIMARY KEY AUTOINCREMENT,digest TEXT UNIQUE,name TEXT,asset TEXT); CREATE TABLE IF NOT EXISTS source_regions(asset TEXT PRIMARY KEY,payload TEXT);')
            for serial,id,name,source,asset,thumb,w,h in self.conn.execute('SELECT serial,id,name,source,asset,thumb,width,height FROM photos WHERE deleted=0 ORDER BY serial'):
                self.items.append(PreparedPhoto(name,None,source,id,asset,serial,thumb,(w,h)))
    def add(self,name,image,source=''):
        if self.conn is None and sum(p.image.width*p.image.height for p in self.items)+image.width*image.height>self.max_pixels:
            raise ValueError('The crop tray is full. Remove unused crops before adding more.')
        item=PreparedPhoto(name,image.copy() if self.conn is None else None,source,dimensions=image.size)
        if self.conn:
            with self.lock,self.conn:
                cursor=self.conn.execute('INSERT INTO photos(id,name,source,asset,thumb,width,height) VALUES(?,?,?,?,?,?,?)',(item.id,name,source,'','',image.width,image.height));item.serial=cursor.lastrowid
                folder=self.root/'photos';folder.mkdir(exist_ok=True);path=folder/(f'{item.serial:06d}_'+item.id+'.png');tmp=path.with_suffix('.tmp');thumb=path.with_suffix('.thumb.jpg')
                try:
                    image.save(tmp,format='PNG');tmp.replace(path);small=image.convert('RGB');small.thumbnail((180,210));small.save(thumb,quality=90)
                    item.asset=str(path);item.thumb=str(thumb);self.conn.execute('UPDATE photos SET asset=?,thumb=? WHERE id=?',(item.asset,item.thumb,item.id))
                finally:
                    if tmp.exists():tmp.unlink()
        else:item.serial=max((p.serial for p in self.items),default=0)+1
        self.items.append(item);return item
    def remove(self,ids):
        if self.conn:
            with self.lock,self.conn:self.conn.executemany('UPDATE photos SET deleted=1 WHERE id=?',[(id,) for id in ids])
        self.items[:]=[p for p in self.items if p.id not in ids]
    def rename(self,item,name):
        name=name.strip()
        if not name:raise ValueError('Enter a photo name.')
        if self.conn:
            with self.lock,self.conn:self.conn.execute('UPDATE photos SET name=? WHERE id=?',(name,item.id))
        item.name=name
    def import_source(self,path):
        if not self.conn:return str(Path(path).resolve())
        with open(path,'rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        with self.lock,self.conn:
            row=self.conn.execute('SELECT asset FROM sources WHERE digest=?',(digest,)).fetchone()
            if row and Path(row[0]).exists():return row[0]
            folder=self.root/'sources';folder.mkdir(exist_ok=True);target=folder/(digest+Path(path).suffix.lower());tmp=target.with_suffix('.tmp')
            try:shutil.copyfile(path,tmp);tmp.replace(target)
            finally:
                if tmp.exists():tmp.unlink()
            self.conn.execute('INSERT OR REPLACE INTO sources(digest,name,asset) VALUES(?,?,?)',(digest,Path(path).name,str(target)));return str(target)
    def sources(self):
        if not self.conn:return []
        with self.lock:return self.conn.execute('SELECT serial,name,asset FROM sources ORDER BY serial').fetchall()
    def save_regions(self,path,regions):
        if self.conn:
            from dataclasses import asdict
            with self.lock,self.conn:self.conn.execute('INSERT OR REPLACE INTO source_regions VALUES(?,?)',(path,json.dumps([asdict(r) for r in regions])))
    def load_regions(self,path):
        if not self.conn:return None
        with self.lock:row=self.conn.execute('SELECT payload FROM source_regions WHERE asset=?',(path,)).fetchone()
        return [CropRegion(**r) for r in json.loads(row[0])] if row else None
    def close(self):
        if self.conn:self.conn.close();self.conn=None
    def materialize(self,item,folder):
        """Only selected crops become durable job assets; unused crops stay in memory."""
        if item.asset and Path(item.asset).is_file():return item.asset
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);path=folder/(item.id+'.png');tmp=path.with_suffix('.tmp')
        try:item.image.save(tmp,format='PNG');tmp.replace(path)
        finally:
            if tmp.exists():tmp.unlink()
        item.asset=str(path);return item.asset

def order_quad(points):
    import numpy as np
    pts=np.array(points,dtype=np.float32)
    center=pts.mean(axis=0);angles=np.arctan2(pts[:,1]-center[1],pts[:,0]-center[0]);pts=pts[np.argsort(angles)]
    start=np.argmin(pts.sum(axis=1));pts=np.roll(pts,-int(start),axis=0)
    return pts

def detect_photo_regions(image):
    """Detect separate paper prints on light scanner beds; never merge people by face."""
    import cv2
    import numpy as np
    sample=image.convert('RGB').copy();sample.thumbnail((1800,1800));arr=np.asarray(sample);gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    grid=detect_regular_grid(sample)
    if grid:
        sx=image.width/sample.width;sy=image.height/sample.height
        return [CropRegion([(x*sx,y*sy) for x,y in r.points]) for r in grid]
    edges=cv2.Canny(cv2.GaussianBlur(gray,(3,3),0),25,80)
    edges=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    total=sample.width*sample.height;candidates=[]
    for contour in contours:
        area=cv2.contourArea(contour)
        if area<total*.007 or area>total*.90:continue
        perimeter=cv2.arcLength(contour,True);approx=cv2.approxPolyDP(contour,.025*perimeter,True)
        if len(approx)!=4 or not cv2.isContourConvex(approx):continue
        quad=order_quad(approx.reshape(4,2));rect_area=abs(cv2.contourArea(quad))
        side_a=float(np.linalg.norm(quad[1]-quad[0]));side_b=float(np.linalg.norm(quad[2]-quad[1]))
        if min(side_a,side_b)<35 or not .42<min(side_a,side_b)/max(side_a,side_b)<=1:continue
        # Prevent near-white sheet/page borders being proposed as a portrait.
        mask=np.zeros(gray.shape,np.uint8);cv2.fillConvexPoly(mask,quad.astype(np.int32),255)
        if np.mean(gray[mask>0]<210)<.12:continue
        candidates.append((rect_area,quad))
    # Content contours recover prints whose faint white borders have broken edges.
    _,ink=cv2.threshold(gray,220,255,cv2.THRESH_BINARY_INV);ink=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    contours,_=cv2.findContours(ink,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        area=cv2.contourArea(c)
        if not total*.007<area<total*.3:continue
        rect=cv2.minAreaRect(c);w,h=rect[1]
        if min(w,h)<35 or min(w,h)/max(w,h)<.55:continue
        candidates.append((w*h,order_quad(cv2.boxPoints(rect))))
    candidates.sort(key=lambda pair:pair[0],reverse=True);kept=[]
    for area,quad in candidates:
        duplicate=False
        for old_area,old in kept:
            overlap,_=cv2.intersectConvexConvex(quad,old)
            if overlap/min(area,old_area)>.65:duplicate=True;break
        if not duplicate:kept.append((area,quad))
    sx=image.width/sample.width;sy=image.height/sample.height
    regions=[CropRegion([(float(x*sx),float(y*sy)) for x,y in quad]) for _,quad in kept]
    # Reading order with tolerance for rotated prints on the same row.
    row_height=max(1,image.height*.12)
    regions.sort(key=lambda r:(round(min(p[1] for p in r.points)/row_height),min(p[0] for p in r.points)))
    return regions

def detect_regular_grid(image):
    """Recover tightly tiled passport sheets even when their borders merge."""
    import cv2
    import numpy as np
    gray=cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2GRAY)
    classifier=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    faces=classifier.detectMultiScale(gray,1.05,4,minSize=(16,16))
    if len(faces)<4:return []
    median_w=float(np.median(faces[:,2]));median_h=float(np.median(faces[:,3]))
    def clusters(values,tolerance):
        groups=[]
        for value in sorted(values):
            if not groups or value-np.mean(groups[-1])>tolerance:groups.append([value])
            else:groups[-1].append(value)
        return [float(np.mean(g)) for g in groups]
    xs=clusters(faces[:,0]+faces[:,2]/2,median_w*.65);ys=clusters(faces[:,1]+faces[:,3]/2,median_h*.65)
    if len(xs)<2 or len(ys)<2 or len(xs)*len(ys)!=len(faces):return []
    dx=float(np.median(np.diff(xs)));dy=float(np.median(np.diff(ys)))
    if not 1.3<dx/median_w<2.8 or not 1.6<dy/median_h<3.1:return []
    if np.std(np.diff(xs))/dx>.15 or np.std(np.diff(ys))/dy>.15:return []
    result=[]
    for x,y,w,h in sorted(faces.tolist(),key=lambda f:(round((f[1]+f[3]/2)/max(1,dy*.5)),f[0])):
        cx=x+w/2;left=max(0,cx-dx*.47);right=min(image.width-1,cx+dx*.47);top=max(0,y+h/2-h*.95);bottom=min(image.height-1,top+dy*.96)
        result.append(CropRegion([(left,top),(right,top),(right,bottom),(left,bottom)]))
    return result

def extract_region(image,region):
    import cv2
    import numpy as np
    quad=order_quad(region.points)
    if not np.isfinite(quad).all() or not cv2.isContourConvex(quad):raise ValueError('Crop corners must form a valid four-sided area.')
    width=round(max(np.linalg.norm(quad[1]-quad[0]),np.linalg.norm(quad[2]-quad[3])))
    height=round(max(np.linalg.norm(quad[3]-quad[0]),np.linalg.norm(quad[2]-quad[1])))
    if min(width,height)<20 or width*height>50_000_000:raise ValueError('Crop is too small or too large. Adjust its corners.')
    target=np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]],np.float32)
    transform=cv2.getPerspectiveTransform(quad,target)
    result=Image.fromarray(cv2.warpPerspective(np.asarray(image.convert('RGB')),transform,(width,height),borderMode=cv2.BORDER_REPLICATE))
    if region.rotation:result=result.rotate(region.rotation,expand=True)
    return result

def orient_portrait(image):
    """Orient extracted prints/phone portraits using a local frontal-face cascade."""
    import cv2
    import numpy as np
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    sample=image.convert('RGB').copy();sample.thumbnail((640,640));best=None
    for angle in (0,90,180,270):
        rotated=sample.rotate(angle,expand=True);gray=cv2.cvtColor(np.asarray(rotated),cv2.COLOR_RGB2GRAY)
        faces,_,weights=cascade.detectMultiScale3(gray,1.1,5,minSize=(25,25),outputRejectLevels=True)
        if len(faces):
            score=max(float(weight) for weight in weights)
            if best is None or score>best[0]:best=(score,angle)
    return (image.rotate(best[1],expand=True) if best and best[1] else image),bool(best)
