import os
import tempfile
from collections import OrderedDict
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from app.services.layout import mm_to_pt as pt,page_size,validate_layout
from app.services.imaging import render_photo

def export_pdf(job,path,current_page=None,dpi=300):
    validate_layout(job)
    if not job.photos:raise ValueError('Add photographs before exporting.')
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(suffix='.pdf',dir=target.parent); os.close(fd)
    try:
        pw,ph=page_size(job.print_settings); c=canvas.Canvas(tmp,pagesize=(pt(pw),pt(ph)))
        c.setTitle(job.name); photos={p.id:p for p in job.photos}; images=OrderedDict()
        pages=[current_page] if current_page is not None else range(job.page_count)
        for page in pages:
            for r in job.placements:
                if r.page!=page:continue
                p=photos[r.photo_id]
                if p.id not in images:images[p.id]=ImageReader(render_photo(p,dpi))
                images.move_to_end(p.id)
                while len(images)>4:images.popitem(last=False)
                x,y,w,h=pt(r.x),pt(ph-r.y-r.height),pt(r.width),pt(r.height)
                if not r.rotation:c.drawImage(images[p.id],x,y,w,h)
                else:
                    c.saveState()
                    if r.rotation==90:c.translate(x,y+h);c.rotate(-90)
                    elif r.rotation==270:c.translate(x+w,y);c.rotate(90)
                    else:c.translate(x+w,y+h);c.rotate(180)
                    c.drawImage(images[p.id],0,0,pt(p.width),pt(p.height));c.restoreState()
                if p.border and p.border_mm:
                    b=pt(p.border_mm); c.setStrokeColor(HexColor(p.border_color)); c.setLineWidth(b); c.rect(x+b/2,y+b/2,w-b,h-b,stroke=1,fill=0)
                if job.print_settings.get('guides'):
                    c.setStrokeColor(HexColor('#808080')); c.setLineWidth(pt(.1))
                    for cx,cy,sx,sy in [(x,y,-1,-1),(x+w,y,1,-1),(x,y+h,-1,1),(x+w,y+h,1,1)]:
                        c.line(cx+sx*pt(.5),cy,cx+sx*pt(2),cy);c.line(cx,cy+sy*pt(.5),cx,cy+sy*pt(2))
            c.showPage()
        c.save(); os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return str(target)

def calibration_pdf(path,scale=1.):
    c=canvas.Canvas(str(path),pagesize=(pt(210),pt(297)))
    c.setFont('Helvetica',12);c.drawString(pt(20),pt(275),'Studio Photo Maker - printer calibration')
    c.drawString(pt(20),pt(264),'Print at Actual Size / 100%. Measure the square: target 100 x 100 mm.')
    c.setLineWidth(pt(.2));c.rect(pt(30),pt(130),pt(100*scale),pt(100*scale))
    for n in range(101):
        x=pt(30+n*scale);c.line(x,pt(110),x,pt(110+(5 if n%10==0 else 2)))
    c.drawString(pt(20),pt(90),f'Applied calibration factor: {scale:.6f}. Photo PDFs always keep exact nominal dimensions.')
    c.save();return str(path)
