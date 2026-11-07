"""Local document/copy/card sessions. Pixels and physical placement stay separate."""
from dataclasses import dataclass,field
from pathlib import Path
import json,uuid,math,shutil,time
from PIL import Image,ImageOps,ImageEnhance
from app.models.domain import Job,Photo,Layer,Placement
from app.services.layout import validate_layout
from app.services.cropping import CropRegion,extract_region,detect_photo_regions

PAPERS={'A4':(210.,297.),'A5':(148.,210.),'Letter':(215.9,279.4),'Legal':(215.9,355.6),'4 × 6 in':(101.6,152.4),'5 × 7 in':(127.,177.8)}

@dataclass
class DocumentPage:
    source:str
    dpi:float=300.
    points:list=field(default_factory=list)
    rotation:int=0
    label:str='Page'
    dpi_trusted:bool=True

class DocumentSession:
    def __init__(self,root,kind='copy'):
        self.root=Path(root)/'document-sessions'/uuid.uuid4().hex;self.root.mkdir(parents=True,exist_ok=False)
        self.kind=kind;self.pages=[];self.keep=False;self.generation=0;self.input_paths=[]
        self.manifest()
    def manifest(self,settings=None,force=False):
        if self.keep and not force and (self.root/'session.json').is_file():return
        from dataclasses import asdict
        records=[]
        for p in self.pages:
            record=asdict(p);record['source']=str(Path(p.source).relative_to(self.root));records.append(record)
        payload=dict(kind=self.kind,keep=self.keep,pages=records,settings=settings or {},input_paths=self.input_paths)
        temporary=self.root/'session.tmp';temporary.write_text(json.dumps(payload),encoding='utf-8');temporary.replace(self.root/'session.json')
    def import_image(self,path,dpi=None,label='Page'):
        path=Path(path)
        with Image.open(path) as original:
            if original.width*original.height>80_000_000:raise ValueError('Image exceeds the 80 megapixel document limit')
            original.verify()
        with Image.open(path) as image:trusted=dpi is not None or 'dpi' in image.info;reported=image.info.get('dpi',(300,300))[0]
        dpi=dpi or reported
        if not isinstance(dpi,(int,float)) or not math.isfinite(dpi) or not 50<=dpi<=9600:raise ValueError('Set a trustworthy scan DPI between 50 and 9600')
        target=self.root/(uuid.uuid4().hex+path.suffix.lower());shutil.copyfile(path,target)
        self.input_paths.append(str(path.resolve()))
        page=DocumentPage(str(target),float(dpi),label=label,dpi_trusted=trusted);self.pages.append(page);self.manifest();return page
    def prepared(self,page,settings):
        import hashlib
        key=hashlib.sha256(json.dumps(dict(source=page.source,mtime=Path(page.source).stat().st_mtime_ns,points=page.points,rotation=page.rotation,settings=settings),sort_keys=True).encode()).hexdigest()
        # Bound internal cache names so sibling restore staging stays usable on
        # Windows installations without long-path support. Export names/pixels
        # are unchanged; old saved-job paths remain valid.
        target=self.root/('processed-'+key[:32]+'.png')
        if target.is_file():
            with Image.open(target) as cached:return str(target),cached.size
        with Image.open(page.source) as raw:
            if raw.width*raw.height>80_000_000:raise ValueError('Document exceeds pixel budget')
            rgba=ImageOps.exif_transpose(raw).convert('RGBA');image=Image.new('RGBA',rgba.size,'white');image.alpha_composite(rgba);image=image.convert('RGB')
        if page.points:image=extract_region(image,CropRegion(page.points))
        if page.rotation:image=image.rotate(-page.rotation,expand=True)
        color=settings.get('color','color')
        if color=='gray':image=ImageOps.grayscale(image).convert('RGB')
        elif color=='mono':image=ImageOps.grayscale(image).point(lambda v:255 if v>=160 else 0).convert('RGB')
        for key,enhancer in [('brightness',ImageEnhance.Brightness),('contrast',ImageEnhance.Contrast),('sharpness',ImageEnhance.Sharpness)]:
            value=float(settings.get(key,1.))
            if not math.isfinite(value) or not 0<=value<=3:raise ValueError('Invalid document adjustment')
            if value!=1:image=enhancer(image).enhance(value)
        image.save(target,dpi=(page.dpi,page.dpi))
        return str(target),image.size
    def import_pdf(self,path):
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtCore import QSize
        original=self.root/(uuid.uuid4().hex+'.pdf');shutil.copyfile(path,original);self.input_paths.append(str(Path(path).resolve()));document=QPdfDocument()
        if document.load(str(original))!=QPdfDocument.Error.None_:raise ValueError('Could not open PDF')
        if not 1<=document.pageCount()<=100:raise ValueError('Import PDF files with 1–100 pages')
        pages=[]
        for index in range(document.pageCount()):
            size=document.pagePointSize(index);width,height=round(size.width()/72*300),round(size.height()/72*300)
            if width*height>50_000_000:raise ValueError('PDF page exceeds the 50 megapixel rendering limit')
            image=document.render(index,QSize(width,height));target=self.root/(uuid.uuid4().hex+'.png')
            if image.isNull() or not image.save(str(target)):raise ValueError('Could not render PDF page')
            page=DocumentPage(str(target),300,label=f'Page {index+1}');self.pages.append(page);pages.append(page)
        document.close();self.manifest();return pages
    @classmethod
    def open(cls,path):
        path=Path(path).resolve();data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('pages'),list) or not isinstance(data.get('settings',{}),dict):raise ValueError('Invalid document session structure')
        if data.get('kind') not in ('copy','nid') or not data.get('keep'):raise ValueError('Not a saved document session')
        session=object.__new__(cls);session.root=path.parent;session.kind=data['kind'];session.keep=True;session.generation=0;session.pages=[];session.input_paths=data.get('input_paths',[])
        for raw in data['pages']:
            record=dict(raw);source=(path.parent/record['source']).resolve()
            if not source.is_relative_to(path.parent) or not source.is_file():raise ValueError('Saved session asset missing or outside session')
            record['source']=str(source);session.pages.append(DocumentPage(**record))
        return session
    def job(self,settings):
        if not self.pages:raise ValueError('Scan or import a page first')
        paper=tuple(settings.get('paper_mm',PAPERS.get(settings.get('paper','A4'),PAPERS['A4'])))
        if len(paper)!=2 or any(not math.isfinite(v) or not 50<=v<=1000 for v in paper):raise ValueError('Invalid paper dimensions')
        landscape=bool(settings.get('landscape',False));pw,ph=paper[::-1] if landscape else paper
        margin=float(settings.get('margin',10));copies=int(settings.get('copies',1))
        if not 1<=copies<=100 or not 0<=margin<min(pw,ph)/2:raise ValueError('Invalid copies or margins')
        job=Job(name='BD NID copy' if self.kind=='nid' else 'Document copy',print_settings=dict(policy='document',document_paper_mm=list(paper),landscape=landscape,margin=margin,enforce_margins=True,dpi=300))
        sizes=[]
        for page in self.pages:
            if not page.dpi_trusted and (settings.get('scale_mode','actual')!='fit' and (self.kind!='nid' or settings.get('actual_card'))):raise ValueError('Physical size is unknown. Verify the imported page DPI or explicitly choose Fit.')
            path,(w,h)=self.prepared(page,settings)
            width,height=w/page.dpi*25.4,h/page.dpi*25.4
            if self.kind=='nid':
                bounds=(float(settings.get('card_width',85.6)),float(settings.get('card_height',53.98)))
                scale=1 if settings.get('actual_card',False) else min(bounds[0]/width,bounds[1]/height)
            else:
                mode=settings.get('scale_mode','actual')
                scale=min((pw-2*margin)/width,(ph-2*margin)/height) if mode=='fit' else float(settings.get('scale',100))/100 if mode=='custom' else 1.
            if not math.isfinite(scale) or scale<=0:raise ValueError('Scale must be positive')
            width*=scale;height*=scale
            photo=Photo(name=page.label,width=width,height=height,quantity=copies,border=False,background='white',layers=[Layer(path)])
            job.photos.append(photo);sizes.append((width,height))
        if self.kind=='nid':
            if len(job.photos)!=2:raise ValueError('Review both Front and Back before printing')
            spacing=float(settings.get('spacing',10));top=float(settings.get('top',20));pairs=int(settings.get('pairs_per_sheet',1))
            centered=bool(settings.get('center',False))
            if not 0<=spacing<=100 or not 1<=pairs<=10 or (not centered and (not math.isfinite(top) or top<margin)):raise ValueError('Invalid card spacing or position')
            group_height=sum(h for _,h in sizes)+spacing
            for copy in range(copies):
                page=copy//pairs
                count=min(pairs,copies-page*pairs)
                batch_height=count*group_height+(count-1)*spacing
                start=(ph-batch_height)/2 if centered else top
                y=start+(copy%pairs)*(group_height+spacing)
                for photo,(width,height) in zip(job.photos,sizes):
                    alignment='center' if centered else settings.get('align','center');x=margin if alignment=='left' else pw-margin-width if alignment=='right' else (pw-width)/2
                    job.placements.append(Placement(photo.id,copy,page,x,y,width,height));y+=height+spacing
            job.page_count=math.ceil(copies/pairs)
        else:
            for copy in range(copies):
                for index,(photo,(width,height)) in enumerate(zip(job.photos,sizes)):
                    x=(pw-width)/2 if settings.get('center',True) else margin
                    y=(ph-height)/2 if settings.get('center',True) else margin
                    job.placements.append(Placement(photo.id,copy,copy*len(job.photos)+index,x,y,width,height))
            job.page_count=copies*len(job.photos)
        validate_layout(job);return job
    def cleanup(self,protected=()):
        if self.keep:return False
        base=self.root.resolve()
        if base.parent.name!='document-sessions' or self.root.is_symlink() or self.root.is_junction() or self.root.parent.is_symlink() or self.root.parent.is_junction():raise ValueError('Unsafe session cleanup path')
        if any(Path(p).resolve().is_relative_to(base) for p in protected):return False
        # Only the owned UUID directory is removed. Retained manifests are never purged.
        if len(base.name)!=32 or any(c not in '0123456789abcdef' for c in base.name):raise ValueError('Invalid session identity')
        if base.exists():shutil.rmtree(base)
        return True

    def export_image(self,page,settings,path):
        """Write the processed view atomically; caller applies protected-target policy."""
        import os
        path=Path(path);suffix=path.suffix.lower()
        if suffix not in ('.png','.jpg','.jpeg'):raise ValueError('Choose a .png, .jpg or .jpeg filename; extensions are not appended')
        processed,_=self.prepared(page,settings);temporary=path.parent/(uuid.uuid4().hex+'.tmp')
        try:
            with Image.open(processed) as image:
                with temporary.open('xb') as stream:
                    image.save(stream,format='PNG' if suffix=='.png' else 'JPEG',dpi=(page.dpi,page.dpi),**({} if suffix=='.png' else {'quality':95}));stream.flush();os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary.exists():temporary.unlink()
        return str(path)

def detect_cards(image):
    """Non-overlapping card boundaries, in reading order; never infer identity."""
    import cv2,numpy as np
    preview=image.convert('RGB').copy();preview.thumbnail((1800,1800));a=np.asarray(preview)
    gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY);gray=cv2.GaussianBlur(gray,(5,5),0);candidates=[]
    # Pale cards on a white scanner bed need weak edges as well as the original
    # high-contrast pass. A bounded closing joins short gaps at rounded corners;
    # it runs only on detection previews and never changes source/export pixels.
    for low,high in ((40,130),(20,60),(10,35)):
        edges=cv2.Canny(gray,low,high)
        for mask in (edges,cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))):
            contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area=cv2.contourArea(contour)
                if area<preview.width*preview.height*.015:continue
                quad=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
                if len(quad)==4 and cv2.isContourConvex(quad):
                    _,_,w,h=cv2.boundingRect(quad)
                    if 1.15<max(w,h)/max(1,min(w,h))<2.6:candidates.append((area,quad.reshape(4,2)))
    from app.services.cropping import order_quad
    kept=[]
    for area,raw in sorted(candidates,key=lambda x:x[0],reverse=True):
        points=order_quad(raw)
        # A scan-bed/page outline is not one of the cards on that page.
        x,y,w,h=cv2.boundingRect(raw)
        if area>preview.width*preview.height*.8 and (x<5 or y<5):continue
        if any(cv2.intersectConvexConvex(points,old)[0]/min(area,old_area)>.6 for old_area,old in kept):continue
        kept.append((area,points))
    sx,sy=image.width/preview.width,image.height/preview.height
    result=[[(float(x*sx),float(y*sy)) for x,y in points] for _,points in kept]
    result.sort(key=lambda points:(round(min(y for x,y in points)/max(1,image.height*.12)),min(x for x,y in points)))
    return result


def detect_card(image):
    regions=detect_cards(image)
    if not regions:return []
    from app.services.cropping import order_quad
    import cv2
    return max(regions,key=lambda points:cv2.contourArea(order_quad(points)))


def propose_card(page):
    """Map a bounded detection preview back to EXIF-oriented source pixels."""
    from app.services.imaging import load_image
    preview=load_image(page.source,1500)
    with Image.open(page.source) as original:size=ImageOps.exif_transpose(original).size
    return [[(x*size[0]/preview.width,y*size[1]/preview.height) for x,y in points] for points in detect_cards(preview)]
