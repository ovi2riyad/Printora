"""Hardware contracts, actual Qt events/processes and PDF round trips, without physical I/O."""
import copy
import hashlib
import json
import os
import time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QPushButton,QScrollArea
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtGui import QPageSize,QPageLayout
from PySide6.QtPdf import QPdfDocument
from pypdf import PdfReader
from app.services.hardware import (HARDWARE_DEFAULTS,ScannerManager,WiaBackend,
    PrintableArea,new_scan_folder,inspect_scan,check_scan_request,preflight_print,page_pixels)
from app.services.layout import auto_layout,page_size
from app.models.domain import Job,Photo,Layer
from app.services.pdf import export_pdf
from app.services.cropping import CropTray
from app.core.database import Database


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait_until(predicate, seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        QApplication.processEvents();time.sleep(.01)
        if predicate():return
    pytest.fail('Timed out waiting for hardware test callback')


def caps():
    return dict(id='flatbed',name='Flatbed',width_mm=210,height_mm=297,
                resolutions=[100,300,600],colors=['color','gray'],formats=['bmp'])


@pytest.fixture
def studio(app,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user'))
    from app.ui.studio_window import StudioWindow
    w=StudioWindow();w.show();app.processEvents()
    warnings=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:warnings.append(str(args[-1])))
    monkeypatch.setattr(QMessageBox,'information',lambda *args:None)
    yield w,warnings
    w.hardware.printing=False;w.hardware.shutdown()
    w.dirty=False;w.timer.stop();w.invalidate_autosave();w.pool.waitForDone()
    QApplication.processEvents();w.dirty=False;w.close();app.processEvents()


def make_job(tmp_path,landscape=False,quantity=4):
    source=tmp_path/'original.png'
    Image.new('RGB',(450,550),'red').save(source,dpi=(300,300))
    photo=Photo(quantity=quantity,border=False,layers=[Layer(str(source))])
    job=Job(photos=[photo],print_settings=dict(landscape=landscape,margin=10,gap_x=.2,gap_y=.2))
    job.placements=auto_layout(job.photos,job.print_settings)
    job.page_count=max(p.page for p in job.placements)+1
    return job,source


@pytest.mark.parametrize('dpi',[100,300,600])
@pytest.mark.parametrize('color',['color','gray'])
def test_dynamic_scan_settings(dpi,color):
    check_scan_request(caps(),dpi,color,[0,0,210,297])
    request=ScannerManager().request('scan',dpi=dpi,color=color)
    assert request==dict(action='scan',dpi=dpi,color=color)


@pytest.mark.parametrize('dpi,color,region',[
    (200,'color',[0,0,210,297]),(300,'mono',[0,0,210,297]),
    (True,'color',[0,0,210,297]),(300,'color',[-1,0,210,297]),
    (300,'color',[0,0,211,297]),(300,'color',[0,0,210,298]),
    (300,'color',[0,0,0,297]),(300,'color',[0,0,float('nan'),297]),
    (300,'color',[0,0,210]),(300,'color',[0,0,210,float('inf')]),
])
def test_invalid_scan_requests_fail_before_driver(dpi,color,region):
    with pytest.raises(ValueError):check_scan_request(caps(),dpi,color,region)


def test_large_scan_rejected_without_automatic_downsampling():
    reported=dict(caps(),resolutions=[9600])
    with pytest.raises(ValueError,match='80 megapixels'):
        check_scan_request(reported,9600,'color',[0,0,210,297])


def test_no_implicit_backend_retry():
    calls=[]
    class BrokenBackend:
        def request(self,*args,**kwargs):
            calls.append(args);raise ValueError('Device disconnected')
    with pytest.raises(ValueError,match='disconnected'):
        ScannerManager(BrokenBackend()).request('scan')
    assert len(calls)==1
    with pytest.raises(ValueError):WiaBackend().request('twain_fallback')


@pytest.mark.parametrize('mode',['RGB','L'])
@pytest.mark.parametrize('dpi',[300,600])
def test_scan_original_bytes_pixels_dpi_and_library_restart(tmp_path,mode,dpi):
    folder=new_scan_folder(tmp_path);source=folder/'original.bmp'
    image=Image.new(mode,(500,700),120);image.save(source,dpi=(dpi,dpi))
    before=source.read_bytes();result=inspect_scan(source,folder,dict(backend='wia',dpi=dpi))
    assert result['width']==500 and result['height']==700 and result['mode']==mode
    assert abs(result['metadata_dpi'][0]-dpi)<.1
    assert result['sha256']==hashlib.sha256(before).hexdigest()
    assert source.read_bytes()==before
    root=tmp_path/'library';tray=CropTray(root=root)
    first=tray.import_source(source);second=tray.import_source(source)
    assert first==second
    assert Path(first).read_bytes()==before
    tray.close();tray=CropTray(root=root)
    assert tray.import_source(source)==first
    tray.close();assert source.read_bytes()==before
    with pytest.raises(FileExistsError):inspect_scan(source,folder,{})
    assert source.read_bytes()==before


@pytest.mark.parametrize('content',[b'not an image',b'BM'+b'\x00'*55])
def test_corrupt_scan_retained_for_recovery(tmp_path,content):
    folder=new_scan_folder(tmp_path);path=folder/'original.bmp';path.write_bytes(content)
    with pytest.raises((OSError,ValueError)):inspect_scan(path,folder,{})
    assert path.read_bytes()==content and not (folder/'provenance.json').exists()


def test_truncated_bitmap_is_not_reported_complete(tmp_path):
    folder=new_scan_folder(tmp_path);path=folder/'original.bmp';Image.new('RGB',(100,100)).save(path)
    data=path.read_bytes()[:100];path.write_bytes(data)
    with pytest.raises(OSError):inspect_scan(path,folder,{})
    assert path.read_bytes()==data


def test_scan_path_escape_rejected(tmp_path):
    folder=new_scan_folder(tmp_path);source=tmp_path/'outside.png';Image.new('RGB',(10,10)).save(source)
    before=source.read_bytes()
    with pytest.raises(ValueError,match='outside'):inspect_scan(source,folder,{})
    assert source.read_bytes()==before


@pytest.mark.parametrize('key,raw',[
    ('scan_dpi','{}'),('scan_dpi','true'),('scan_dpi','9601'),('scan_dpi','"600"'),
    ('scan_color','"cmyk"'),('scanner_backend','"twain"'),('scanner_id','[]'),
    ('preferred_printer','null'),('scan_source','42'),('scanner_id','{bad json'),
])
def test_pa002_hardware_optional_preferences_recover_without_rewriting(tmp_path,key,raw):
    db=Database(tmp_path/'studio.db')
    with db.conn:db.conn.execute('INSERT INTO config VALUES(?,?)',(key,raw))
    assert db.get(key,HARDWARE_DEFAULTS[key])==HARDWARE_DEFAULTS[key]
    assert db.conn.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()[0]==raw
    assert db.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    db.conn.close()


@pytest.mark.parametrize('count',[0,1,3])
def test_dashboard_device_selection_count_and_remembering(studio,count):
    w,_=studio;hub=w.hardware
    rows=[dict(id=str(i),name=f'Scanner {i}',backend='wia',status='Detected') for i in range(count)]
    hub.scan_action='devices';hub.scanner_result(dict(devices=rows))
    assert hub.scanner.count()==max(1,count)
    assert hub.scanner.currentData()==('0' if count else None)
    if count:
        hub.scanner.setCurrentIndex(count-1);hub.select_scanner()
        assert w.db.get('scanner_id')==str(count-1)
    assert isinstance(w.studio.dashboard,QScrollArea)
    assert hub.panel.isVisible()


def test_printer_default_preference_disconnect_reconnect(studio):
    w,_=studio;hub=w.hardware
    rows=[dict(id='A',name='A',status='Queue available',default=False),dict(id='B',name='B',status='Offline',default=True)]
    hub.printer_result(dict(printers=rows));assert hub.printer.currentData()=='B'
    hub.printer.setCurrentIndex(0);hub.select_printer();assert w.db.get('preferred_printer')=='A'
    hub.printer_result(dict(printers=[]));assert hub.printer.currentData() is None
    hub.printer_result(dict(printers=rows));assert hub.printer.currentData()=='A'
    assert 'physical' not in hub.printer.currentText() # queue status is separate from identity


def setup_scan(w,monkeypatch):
    from app.ui.hardware import ScanDialog
    hub=w.hardware;hub.scanners=[dict(id='scanner',name='Test scanner',status='Detected',backend='wia')]
    hub.scan_action='devices';hub.scanner_result(dict(devices=hub.scanners))
    dialog=ScanDialog(hub);hub.scan_dialog=dialog;dialog.show()
    requests=[]
    monkeypatch.setattr(hub.scan_process,'start',lambda *args:requests.append(args))
    monkeypatch.setattr(dialog.verifier,'start',lambda *args:requests.append(args))
    dialog.result('capabilities',dict(sources=[caps()],status='Ready'))
    return hub,dialog,requests


def test_scan_completion_does_not_adopt_or_save_active_job(studio,tmp_path,monkeypatch):
    w,_=studio;hub,dialog,requests=setup_scan(w,monkeypatch)
    job,source=make_job(tmp_path);w.adopt_job(job);w.dirty=True
    token=w._save_generation;original=copy.deepcopy(w.job.to_dict())
    dialog.scan();assert requests[-1][1]['dpi']==300
    path=dialog.folder/'original.bmp';Image.new('RGB',(20,30)).save(path)
    # Operator changes view while acquisition is active; callback only fills the scan dialog.
    w.stack.setCurrentIndex(0);dialog.result('scan',dict(path=str(path),canceled=False))
    assert w.job.to_dict()==original and w.dirty and w._save_generation==token
    assert requests[-1][1]['action']=='inspect_scan'
    monkeypatch.setattr(w,'run',lambda function,done,*args:done(function()))
    dialog.verified(inspect_scan(path,dialog.folder,{}))
    assert w.job.to_dict()==original and w.dirty and dialog.open_button.isEnabled()
    imported=[]
    monkeypatch.setattr(w,'open_cropper',lambda **kwargs:False)
    monkeypatch.setattr(w.cropper,'import_sources',lambda **kwargs:imported.append(kwargs))
    dialog.open_cropper();assert not imported
    monkeypatch.setattr(w,'open_cropper',lambda **kwargs:True)
    dialog.open_cropper();assert imported==[dict(paths=[str(path)])]
    assert path.exists()


def test_scan_cancel_and_shutdown_protect_inflight_transfer(studio,monkeypatch):
    w,_=studio;hub,dialog,requests=setup_scan(w,monkeypatch)
    dialog.scan();folder=dialog.folder
    monkeypatch.setattr(type(hub.scan_process),'active',property(lambda self:True))
    count=len(requests);dialog.scan();assert len(requests)==count
    dialog.cancel();assert (folder/'cancel.request').exists()
    assert hub.operation_active()
    w.close();assert w.isVisible() and w.db.conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    # No completed or partial file is removed by cancel or window close.
    result=folder/'original.bmp';result.write_bytes(b'preserve partial diagnostic')
    dialog.reject();assert result.read_bytes()==b'preserve partial diagnostic'


@pytest.mark.parametrize('landscape',[False,True])
@pytest.mark.parametrize('quantity',[1,4,19])
def test_pdf_to_qprinter_exact_page_and_photo_footprints(app,tmp_path,landscape,quantity):
    from app.services.windows_printing import print_pdf
    job,source=make_job(tmp_path,landscape,quantity);before=source.read_bytes()
    original=tmp_path/'authoritative.pdf';output=tmp_path/'driver-output.pdf';export_pdf(job,original)
    printer=QPrinter(QPrinter.HighResolution);printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(output))
    printer.setPageSize(QPageSize(QPageSize.A4));printer.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    printer.setResolution(600)
    states=[];result=print_pdf(printer,original,job,states.append)
    assert result['pages']==job.page_count and len(states)==2 and 'unconfirmed' in states[-1]
    reader=PdfReader(output);assert len(reader.pages)==job.page_count
    width,height=page_size(job.print_settings)
    authoritative=PdfReader(original)
    assert float(authoritative.pages[0].mediabox.width)*25.4/72==pytest.approx(width,abs=.0001)
    assert float(authoritative.pages[0].mediabox.height)*25.4/72==pytest.approx(height,abs=.0001)
    for page in reader.pages:
        # Qt's PDF test device rounds its MediaBox to integer points (up to .176 mm).
        # This is not the authoritative PDF or evidence of physical printer accuracy.
        assert float(page.mediabox.width)*25.4/72==pytest.approx(width,abs=.177)
        assert float(page.mediabox.height)*25.4/72==pytest.approx(height,abs=.177)
    # Render the driver-generated PDF and locate the actual red photograph on physical paper.
    document=QPdfDocument();assert document.load(str(output))==QPdfDocument.Error.None_
    image=document.render(0,__import__('PySide6.QtCore',fromlist=['QSize']).QSize(*page_pixels(width,height)))
    placement=job.placements[0]
    def sample(x,y):return image.pixelColor(round(x/width*image.width()),round(y/height*image.height()))
    assert sample(placement.x+1,placement.y+1).red()>240
    assert sample(placement.x+1,placement.y+1).green()<20
    assert sample(placement.x-1,placement.y+1).green()>240
    assert sample(placement.x+placement.width-1,placement.y+1).green()<20
    document.close();assert source.read_bytes()==before


@pytest.mark.parametrize('side',['left','top','right','bottom'])
def test_printer_clipping_rejected_without_resizing(tmp_path,side):
    job,_=make_job(tmp_path);old=job.to_dict()
    # Layout is centered; derive a deliberately obstructing boundary.
    p=job.placements[0]
    area=PrintableArea(p.x+1 if side=='left' else 0,p.y+1 if side=='top' else 0,
                       p.x+p.width-1 if side=='right' else 210,p.y+p.height-1 if side=='bottom' else 297)
    with pytest.raises(ValueError,match='printable boundary'):preflight_print(job,area)
    assert job.to_dict()==old


def test_pdf_page_count_mismatch_never_begins_submission(app,tmp_path):
    from app.services.windows_printing import print_pdf
    job,_=make_job(tmp_path);pdf=tmp_path/'sheet.pdf';export_pdf(job,pdf)
    job.page_count=2;states=[];printer=QPrinter();printer.setOutputFormat(QPrinter.PdfFormat)
    with pytest.raises(ValueError,match='page count'):print_pdf(printer,pdf,job,states.append)
    assert not states


def test_native_helper_file_protocol_works_without_console(app,tmp_path,monkeypatch):
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'appdata'))
    folder=new_scan_folder(tmp_path);source=folder/'original.bmp';Image.new('RGB',(30,40)).save(source)
    process=HardwareProcess();results=[];errors=[]
    process.succeeded.connect(results.append);process.failed.connect(errors.append)
    process.start('printer',dict(action='inspect_scan',path=str(source),folder=str(folder),provenance={}),30000)
    with pytest.raises(ValueError,match='progress'):process.start('printer',{})
    wait_until(lambda:bool(results or errors),30)
    assert not errors and results[0]['width']==30 and results[0]['height']==40
    assert process.result_path.exists();process.shutdown()


def test_print_dialog_preflight_double_submit_and_no_order_completion(studio,tmp_path,monkeypatch):
    from app.ui.hardware import PrintDialog
    w,_=studio;hub=w.hardware;job,_=make_job(tmp_path);folder=tmp_path/'transaction';folder.mkdir();export_pdf(job,folder/'sheet.pdf')
    hub.printers=[dict(id='Printer',name='Printer',status='Queue available',default=True)]
    calls=[]
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setattr(HardwareProcess,'start',lambda self,*args:calls.append(args))
    dialog=PrintDialog(hub,job,folder);hub.print_dialog=dialog;dialog.show()
    dialog.result(dict(area=vars(PrintableArea(3,3,207,294))))
    assert dialog.submit.isEnabled()
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    QTest.mouseClick(dialog.submit,Qt.LeftButton);dialog.print_now()
    assert len([c for c in calls if c[1]['action']=='print'])==1
    assert hub.printing and dialog.attempted and not dialog.submit.isEnabled()
    before=w.db.conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    dialog.result(dict(status='Submitted to driver; physical output unconfirmed'))
    assert not hub.printing and w.db.conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==before
    assert 'Completed' in dialog.message.text() and 'not marked' in dialog.message.text()


def test_prepared_print_worker_exports_all_pages_and_leaves_editor(studio,tmp_path,monkeypatch):
    w,_=studio;job,_=make_job(tmp_path,quantity=19);old=w.job.to_dict()
    monkeypatch.setattr(w,'run',lambda function,done,*args:done(function()))
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setattr(HardwareProcess,'start',lambda *args:None)
    w.hardware.print_job(job)
    dialog=w.hardware.print_dialog
    assert dialog and len(PdfReader(dialog.folder/'sheet.pdf').pages)==job.page_count
    assert w.job.to_dict()==old and not w.dirty


def test_print_transaction_cannot_be_resubmitted(app,tmp_path,monkeypatch):
    import app.services.windows_printing as printing
    job,_=make_job(tmp_path);folder=tmp_path/'print-spool'/'token';folder.mkdir(parents=True)
    (folder/'status.json').write_text('{"status":"submission uncertain"}')
    monkeypatch.setattr(printing,'configured_printer',lambda *args:(object(),PrintableArea(0,0,210,297)))
    monkeypatch.setattr(printing,'enumerate_printers',lambda:dict(printers=[dict(id='Printer',status='Queue available')]))
    with pytest.raises(ValueError,match='already attempted'):
        printing.dispatch(dict(action='print',printer='Printer',folder=str(folder),job=job.to_dict()))
    assert json.loads((folder/'status.json').read_text())['status']=='submission uncertain'


@pytest.mark.parametrize('mask_size,zoom,rotation,expected',[
    ((2000,2500),1,0,282),((2000,2500),2,0,141),((2000,2500),1,45,282),
    ((4000,5000),1,0,None),((4000,5000),2,90,282),
])
def test_direct_print_quality_uses_actual_processed_asset(tmp_path,mask_size,zoom,rotation,expected):
    from app.services.hardware import direct_print_quality
    original=tmp_path/'large.jpg';mask=tmp_path/'mask.png'
    Image.new('RGB',(6000,7500)).save(original);Image.new('RGBA',mask_size).save(mask)
    photo=Photo(width=180,height=225,layers=[Layer(str(original),str(mask),scale=zoom,rotation=rotation)])
    warnings=direct_print_quality(Job(photos=[photo]))
    assert (not warnings) if expected is None else str(expected) in warnings[0]
    # Hiding the layer removes its quality warning without touching its pixels.
    photo.layers[0].visible=False;assert not direct_print_quality(Job(photos=[photo]))


def test_actual_qprinter_draw_rectangle_is_exact_and_never_fitted(app,tmp_path,monkeypatch):
    import app.services.windows_printing as printing
    job,_=make_job(tmp_path);pdf=tmp_path/'sheet.pdf';export_pdf(job,pdf)
    rectangles=[]
    class Painter:
        def __init__(self,*args):pass
        def begin(self,printer):return True
        def end(self):return True
        def drawImage(self,rect,image):
            if hasattr(rect,'width'):rectangles.append(rect)
    monkeypatch.setattr(printing,'QPainter',Painter)
    printer=QPrinter();printer.setResolution(600);printer.setOutputFormat(QPrinter.PdfFormat)
    printing.print_pdf(printer,pdf,job)
    rect=rectangles[-1]
    assert rect.left()==0 and rect.top()==0
    assert rect.width()/600*25.4==pytest.approx(210,abs=1e-9)
    assert rect.height()/600*25.4==pytest.approx(297,abs=1e-9)
    assert printer.copyCount()==1 and printer.fullPage()


def test_helper_timeout_is_recoverable_and_never_retries(app,tmp_path,monkeypatch):
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user'))
    folder=new_scan_folder(tmp_path);source=folder/'original.bmp';Image.new('RGB',(30,40)).save(source)
    before=source.read_bytes();process=HardwareProcess();errors=[];results=[]
    process.failed.connect(errors.append);process.succeeded.connect(results.append)
    request=dict(action='inspect_scan',path=str(source),folder=str(folder),provenance={})
    process.start('printer',request,1)
    wait_until(lambda:bool(errors),10)
    assert len(errors)==1 and 'timed out' in errors[0] and not results and not process.active
    assert source.read_bytes()==before
    # An explicit subsequent request succeeds; the timeout did not schedule any retry.
    process.start('printer',request,30000);wait_until(lambda:bool(results),30)
    assert len(errors)==1 and source.read_bytes()==before;process.shutdown()


def test_missing_printer_and_unsupported_paper_are_recoverable(app,monkeypatch):
    import app.services.windows_printing as printing
    class Info:
        @staticmethod
        def printerInfo(name):return Info()
        def isNull(self):return True
    monkeypatch.setattr(printing,'QPrinterInfo',Info)
    with pytest.raises(ValueError,match='not found'):printing.configured_printer('Missing',False)
    monkeypatch.setattr(Info,'isNull',lambda self:False)
    monkeypatch.setattr(Info,'supportedPageSizes',lambda self:[QPageSize(QPageSize.Letter)],raising=False)
    with pytest.raises(ValueError,match='A4'):printing.configured_printer('Letter only',False)


def test_printer_margin_units_converted_before_clipping(app,monkeypatch):
    import app.services.windows_printing as printing
    from PySide6.QtCore import QMarginsF
    class Info:
        @staticmethod
        def printerInfo(name):return Info()
        def isNull(self):return False
        def supportedPageSizes(self):return [QPageSize(QPageSize.A4)]
    class Printer:
        HighResolution=QPrinter.HighResolution
        DuplexNone=QPrinter.DuplexNone
        def __init__(self,*args):
            self.layout=QPageLayout(QPageSize(QPageSize.A4),QPageLayout.Portrait,QMarginsF(8.4,8.4,8.4,8.4),QPageLayout.Point,QMarginsF(8.4,8.4,8.4,8.4))
        def setCopyCount(self,*args):pass
        def setDuplex(self,*args):pass
        def setPageSize(self,*args):pass
        def setPageOrientation(self,*args):pass
        def pageLayout(self):return QPageLayout(self.layout)
    monkeypatch.setattr(printing,'QPrinterInfo',Info);monkeypatch.setattr(printing,'QPrinter',Printer)
    _,area=printing.configured_printer('Driver',False)
    assert area.left==pytest.approx(8.4/72*25.4,abs=.01)
    assert area.right==pytest.approx(210-area.left)


def test_scan_error_never_retries_and_preserves_current_document(studio,monkeypatch):
    w,_=studio;hub,dialog,calls=setup_scan(w,monkeypatch)
    original=w.job.to_dict();dialog.scan();count=len(calls)
    hub.scanner_error('Scanner disconnected / driver busy')
    assert len(calls)==count and w.job.to_dict()==original
    assert 'retry explicitly' in dialog.message.text() and dialog.folder.exists()


def test_quick_print_arranges_only_its_snapshot(studio,tmp_path,monkeypatch):
    w,_=studio;job,_=make_job(tmp_path);job.placements=[];original=job.to_dict()
    monkeypatch.setattr(w,'run',lambda fn,done,*args:done(fn()))
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setattr(HardwareProcess,'start',lambda *args:None)
    w.hardware.print_job(job)
    assert w.hardware.print_dialog.job.placements and job.to_dict()==original


@pytest.mark.parametrize('code,status',[(0x80210006,'Busy'),(-2145320955,'Offline'),
    (0x80210009,'Not Found'),(0x80040154,'Driver Unavailable'),(0x8021000E,'Error')])
def test_driver_hresult_has_actionable_status(code,status):
    from app.ui.hardware_process import driver_message
    assert driver_message(dict(hresult=code,error='driver detail')).startswith(status)


def test_shutdown_then_explicit_refresh_restarts_process(app,tmp_path,monkeypatch):
    from app.ui.hardware_process import HardwareProcess
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user'))
    folder=new_scan_folder(tmp_path);source=folder/'original.bmp';Image.new('RGB',(10,10)).save(source)
    process=HardwareProcess();process.shutdown();results=[];process.succeeded.connect(results.append)
    process.start('printer',dict(action='inspect_scan',path=str(source),folder=str(folder),provenance={}),30000)
    wait_until(lambda:bool(results),30);assert results[0]['width']==10;process.shutdown()
