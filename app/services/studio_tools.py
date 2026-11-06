"""Offline contact sheets, receipts, QR lookup, batch preparation and calibration."""
import copy
from contextlib import contextmanager
from decimal import Decimal,InvalidOperation
import math
import os
from pathlib import Path
import re
import tempfile
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from app.models.domain import Job,Photo,Layer
from app.services.layout import mm_to_pt as pt
from app.services.imaging import remove_background,render_bordered_photo
from app.services.framing import frame_photo


@contextmanager
def atomic_output(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(suffix=path.suffix,dir=path.parent);os.close(fd)
    try:
        yield Path(temporary)
        os.replace(temporary,path)
    finally:Path(temporary).unlink(missing_ok=True)


def pdf_font():
    """Use a local TrueType font when available, without shipping Windows fonts."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if 'PrintoraText' in pdfmetrics.getRegisteredFontNames():return 'PrintoraText'
    candidates=[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/n for n in ('Nirmala.ttf','segoeui.ttf','arial.ttf')]
    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont('PrintoraText',str(path)));return 'PrintoraText'
    return 'Helvetica'


def lines(c,text,x,y,width,font,size=10):
    """Wrap user text as plain text, without markup or executable PDF content."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c.setFont(font,size)
    for paragraph in str(text).splitlines() or ['']:
        current=''
        for char in paragraph:
            if stringWidth(current+char,font,size)>width and current:
                c.drawString(x,y,current);y-=size+4;current=''
            current+=char
        c.drawString(x,y,current);y-=size+4
    return y


def contact_sheet(items,path,customer_details=None,include_customer=False,include_mobile=False,include_names=True,columns=4):
    if not items:raise ValueError('Select photos before creating a contact sheet.')
    if not 2<=columns<=6:raise ValueError('Choose 2 to 6 columns.')
    details=customer_details or {};font=pdf_font();rows=5;cell_w=190/columns;cell_h=49
    with atomic_output(path) as temporary:
        c=canvas.Canvas(str(temporary),pagesize=(pt(210),pt(297)));c.setTitle('Printora contact sheet')
        for start in range(0,len(items),columns*rows):
            c.setFont(font,16);c.drawString(pt(10),pt(282),'Printora contact sheet')
            for index,item in enumerate(items[start:start+columns*rows]):
                x=10+(index%columns)*cell_w;y=267-(index//columns)*cell_h
                image=item.thumbnail((300,300));max_w,max_h=pt(cell_w-4),pt(29);scale=min(max_w/image.width,max_h/image.height)
                c.drawImage(ImageReader(image),pt(x)+(max_w-image.width*scale)/2,pt(y)-image.height*scale,image.width*scale,image.height*scale)
                labels=[f'#{item.serial:06d}']
                if include_names:labels.append(item.name[:80])
                customer=details.get(item.id,{})
                if include_customer:labels.append(str(customer.get('name',''))[:80])
                if include_mobile:labels.append(str(customer.get('mobile',''))[:60])
                from reportlab.pdfbase.pdfmetrics import stringWidth
                clipped=[]
                for label in labels:
                    label=' '.join(label.split())
                    while label and stringWidth(label,font,7)>pt(cell_w-4):label=label[:-1]
                    clipped.append(label)
                lines(c,'\n'.join(clipped),pt(x),pt(y-32),pt(cell_w-4),font,7)
            c.setFont(font,8);c.drawString(pt(10),pt(10),f'Page {start//(columns*rows)+1} · photo labels only unless customer fields were selected')
            c.showPage()
        c.save()
    return str(path)


def qr_payload(order_id):
    if not re.fullmatch('[0-9a-f]{32}',order_id):raise ValueError('Invalid local order ID.')
    return 'printora:order:'+order_id


def parse_qr(text):
    match=re.fullmatch(r'printora:order:([0-9a-f]{32})',str(text).strip())
    if not match:raise ValueError('This is not a Printora order code.')
    return match[1]


def qr_image(order_id):
    import cv2
    import numpy as np
    matrix=cv2.QRCodeEncoder_create().encode(qr_payload(order_id))
    matrix=np.pad(matrix,4,constant_values=255)
    return Image.fromarray(matrix).resize((matrix.shape[1]*8,matrix.shape[0]*8),Image.Resampling.NEAREST)


def export_qr(order_id,path):
    with atomic_output(path) as temporary:qr_image(order_id).save(temporary,format='PNG')
    return str(path)


def decode_qr(path):
    import cv2
    import numpy as np
    from app.services.imaging import load_image
    image=np.asarray(load_image(path).convert('RGB'));value,_,_=cv2.QRCodeDetector().detectAndDecode(image)
    return parse_qr(value)


def receipt_pdf(order,job,path,include_name=False,include_mobile=False,include_notes=False,amount='',currency=''):
    try:price=Decimal(str(amount)).quantize(Decimal('.01')) if str(amount).strip() else None
    except InvalidOperation:raise ValueError('Enter a valid optional total price.')
    if price is not None and (not price.is_finite() or price<0 or price>Decimal('999999999.99')):raise ValueError('Price must be a finite non-negative amount.')
    if len(currency)>12:raise ValueError('Use a short currency label.')
    font=pdf_font()
    with atomic_output(path) as temporary:
        c=canvas.Canvas(str(temporary),pagesize=(pt(210),pt(297)));c.setTitle(f'Printora receipt O{order["serial"]:06d}')
        y=pt(280)
        text=[f'Printora — order receipt O{order["serial"]:06d}',f'Date: {order["created"]} (UTC)',f'Status: {order["status"]}']
        if include_name:text.append('Customer: '+order['customer_name'][:200])
        if include_mobile:text.append('Mobile: '+order['customer_mobile'][:100])
        for label in text:y=lines(c,label,pt(15),y,pt(180),font,11)
        y-=12
        for i,p in enumerate(job.photos):
            if y<pt(35):c.showPage();y=pt(280)
            y=lines(c,f'{i+1}. {p.kind} · {p.width:g} × {p.height:g} mm · {p.quantity} copies',pt(15),y,pt(180),font)
        y=lines(c,f'Total copies: {sum(p.quantity for p in job.photos)}',pt(15),y-12,pt(180),font,11)
        if price is not None:y=lines(c,f'Total: {currency.strip()} {price:.2f}',pt(15),y,pt(180),font,11)
        if include_notes:
            for part in str(order.get('notes','')).splitlines():
                for offset in range(0,len(part) or 1,85):
                    if y<pt(30):c.showPage();y=pt(280)
                    y=lines(c,part[offset:offset+85],pt(15),y,pt(180),font)
        c.save()
    return str(path)


def calibration_sheet(path):
    with atomic_output(path) as temporary:
        c=canvas.Canvas(str(temporary),pagesize=(pt(210),pt(297)));font=pdf_font();c.setFont(font,12)
        c.drawString(pt(15),pt(280),'Printora calibration — print at Actual Size / 100%')
        c.setLineWidth(pt(.2));c.rect(pt(35),pt(140),pt(100),pt(100))
        c.setFont(font,10);c.drawString(pt(40),pt(185),'100 × 100 mm reference square')
        for n in range(101):
            length=5 if n%10==0 else 2
            c.line(pt(35+n),pt(125),pt(35+n),pt(125+length))
            c.line(pt(20),pt(140+n),pt(20+length),pt(140+n))
            if n%10==0:
                c.setFont(font,7);c.drawString(pt(34+n),pt(120),str(n));c.drawRightString(pt(18),pt(139+n),str(n))
        c.rect(pt(35),pt(45),pt(45),pt(55));c.rect(pt(95),pt(55),pt(55),pt(45))
        c.setFont(font,10);c.drawString(pt(35),pt(38),'45 × 55 mm');c.drawString(pt(95),pt(48),'55 × 45 mm')
        c.drawString(pt(15),pt(15),'Photo PDFs always retain exact nominal dimensions. Apply any correction in the printer driver.')
        c.save()
    return str(path)


def calibration_profile(width,height):
    if not all(math.isfinite(v) and 50<=v<=150 for v in (width,height)):raise ValueError('Measured sides must be between 50 and 150 mm.')
    return dict(measured_width=width,measured_height=height,driver_x=100/width,driver_y=100/height)


def batch_prepare(items,options,model_dir,root):
    if not 1<=len(items)<=200:raise ValueError('Prepare between 1 and 200 photos per reviewed batch.')
    root=Path(root);results=[]
    for item in items:
        try:
            if not item.asset or not Path(item.asset).is_file():raise ValueError('The prepared image is missing; restore its library asset.')
            joint=item.kind=='Joint';recipe=options.get('recipe')
            if recipe and recipe['kind']!=item.kind:raise ValueError('Recipe category differs from this photo. Select the matching category or automatic sizes.')
            photo=Photo(name=f'Batch #{item.serial:06d}',kind='Combined joint' if joint else 'Individual',width=55 if joint else 45,height=45 if joint else 55,background=options.get('background','#ADD8E6'),provenance={'library_ids':[item.id]})
            settings=dict(margin=10,gap_x=.2,gap_y=.2,landscape=False,layout='auto',enforce_margins=True,dpi=300)
            if recipe:
                from app.services.profiles import apply_profile
                apply_profile(photo,recipe,settings)
            mask=remove_background(item.asset,model_dir,root/'cache',quality=options.get('quality','balanced')) if options.get('remove_background',True) else ''
            layer=Layer(item.asset,mask,label=f'#{item.serial:06d}')
            for field in ('brightness','contrast','saturation','sharpness'):setattr(layer,field,float(options.get(field,1)))
            photo.layers=[layer];frame_photo(photo,options.get('framing','balanced'));job=Job(name=photo.name,photos=[photo],print_settings=settings)
            preview=render_bordered_photo(photo,100);preview.thumbnail((380,380))
            results.append(dict(serial=item.serial,job=job,preview=preview,error='',reviewed=False,saved=False))
        except Exception as e:results.append(dict(serial=item.serial,job=None,preview=None,error=str(e),reviewed=False,saved=False))
    return results


def studio_statistics(db,tray):
    conn=db.conn
    result=dict(customers=conn.execute('SELECT count(*) FROM customers WHERE archived=0').fetchone()[0],orders=conn.execute('SELECT count(*) FROM orders').fetchone()[0])
    result['generated_copies']=conn.execute("SELECT coalesce(sum(i.quantity),0) FROM order_items i WHERE EXISTS(SELECT 1 FROM print_events e WHERE e.order_id=i.order_id AND e.status='Ready')").fetchone()[0]
    result['completed_copies']=conn.execute("SELECT coalesce(sum(i.quantity),0) FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.status='Completed'").fetchone()[0]
    with tray.lock:
        result['prepared_photos']=tray.conn.execute('SELECT count(*) FROM photos').fetchone()[0] if tray.conn else len(tray.items)
        result['unknown_photo_dates']=tray.conn.execute('SELECT count(*) FROM photos WHERE created_at IS NULL').fetchone()[0] if tray.conn else 0
    result['monthly_orders']=conn.execute("SELECT strftime('%Y-%m',created),count(*) FROM orders GROUP BY 1 ORDER BY 1 DESC LIMIT 12").fetchall()
    result['recent_customers']=conn.execute('SELECT serial,name,activity FROM customers WHERE archived=0 ORDER BY activity DESC LIMIT 8').fetchall()
    return result
