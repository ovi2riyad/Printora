import hashlib
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image
from pypdf import PdfReader
from app.services import studio_tools as tools
from app.services.cropping import CropTray
from app.models.domain import Photo,Layer,Job


def test_contact_sheet_pagination_and_privacy(tmp_path):
    tray=CropTray(root=tmp_path/'library');items=[tray.add('Private photo name',Image.new('RGB',(60,80),'red')) for _ in range(21)]
    details={p.id:{'name':'PRIVATE CUSTOMER','mobile':'01712345678'} for p in items}
    out=tmp_path/'contacts.pdf';tools.contact_sheet(items,out,details,include_names=False)
    pages=PdfReader(out).pages;text=''.join(p.extract_text() for p in pages)
    assert len(pages)==2 and '#000021' in text and 'PRIVATE CUSTOMER' not in text and '01712345678' not in text and 'Private photo name' not in text
    tools.contact_sheet(items[:1],out,details,include_customer=True,include_mobile=True)
    text=PdfReader(out).pages[0].extract_text();assert 'PRIVATE CUSTOMER' in text and '01712345678' in text
    tray.close()


def test_local_qr_roundtrip_and_validation(tmp_path):
    id='ab'*16;path=tmp_path/'qr.png';tools.export_qr(id,path)
    assert tools.decode_qr(path)==id and tools.parse_qr(tools.qr_payload(id))==id
    for invalid in ('https://example.com','printora:order:private-name','printora:order:'+id+'/other',''):
        with pytest.raises(ValueError):tools.parse_qr(invalid)
    with pytest.raises(ValueError):tools.qr_payload('customer-mobile')


def test_receipt_optional_private_fields_and_price_validation(tmp_path):
    order=dict(serial=12,created='2026-11-06',status='Draft',customer_name='PRIVATE PERSON',customer_mobile='01712345678',notes='PRIVATE NOTE')
    job=Job(photos=[Photo(quantity=6)]);path=tmp_path/'receipt.pdf'
    tools.receipt_pdf(order,job,path,amount='12.50',currency='BDT');text=PdfReader(path).pages[0].extract_text()
    assert '12.50' in text and '6 copies' in text and 'PRIVATE' not in text and '01712345678' not in text
    tools.receipt_pdf(order,job,path,include_name=True,include_mobile=True,include_notes=True)
    text=PdfReader(path).pages[0].extract_text();assert all(s in text for s in ('PRIVATE PERSON','PRIVATE NOTE','01712345678'))
    for bad in ('NaN','Infinity','-2','not money'):
        before=path.read_bytes()
        with pytest.raises(ValueError):tools.receipt_pdf(order,job,path,amount=bad)
        assert path.read_bytes()==before


def test_exact_calibration_geometry_and_profile(tmp_path):
    from app.services.layout import mm_to_pt
    path=tmp_path/'calibration.pdf';tools.calibration_sheet(path);page=PdfReader(path).pages[0]
    rects=[args for args,operator in page.get_contents().operations if operator==b're']
    assert any(float(a[2])==pytest.approx(mm_to_pt(100),abs=.0001) and float(a[3])==pytest.approx(mm_to_pt(100),abs=.0001) for a in rects)
    assert tools.calibration_profile(99,101)['driver_x']==pytest.approx(100/99)
    for bad in (float('nan'),0,151):
        with pytest.raises(ValueError):tools.calibration_profile(bad,100)


def test_batch_isolates_failures_preserves_assets_and_requires_review(tmp_path):
    tray=CropTray(root=tmp_path/'library');a=tray.add('Good',Image.new('RGB',(60,80),'red'));b=tray.add('Missing',Image.new('RGB',(60,80),'blue'));Path(b.asset).unlink()
    digest=hashlib.sha256(Path(a.asset).read_bytes()).hexdigest()
    results=tools.batch_prepare([a,b],dict(remove_background=False,framing='fit',brightness=1.2),None,tmp_path)
    assert results[0]['job'] and results[1]['error'] and not any(r['reviewed'] or r['saved'] for r in results)
    layer=results[0]['job'].photos[0].layers[0];assert layer.brightness==1.2
    assert hashlib.sha256(Path(a.asset).read_bytes()).hexdigest()==digest
    second=tools.batch_prepare([a],dict(remove_background=False),None,tmp_path)
    assert second[0]['job'].id!=results[0]['job'].id
    tray.close()


def test_tools_ui_review_save_statistics_and_qr_lookup(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from app.ui.studio_window import StudioWindow
    app=QApplication.instance() or QApplication([]);monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'user'));w=StudioWindow();w.notify=lambda *_:None
    try:
        manager=w.studio;page=manager.tools;page.refresh()
        item=w.tray.add('Test',Image.new('RGB',(60,80),'red'));page.prepared(tools.batch_prepare([item],{'remove_background':False},None,w.db.path.parent))
        page.save_reviewed();assert not page.results[0]['saved']
        page.review();page.save_reviewed();assert page.results[0]['saved']
        job=w.db.load_job(page.results[0]['job'].id);order=manager.orders.create(job)
        event,export_job=manager.orders.begin_export(order['id'],tmp_path/'order.pdf')
        manager.orders.finish_export(event,error='deliberate test failure')
        stats=tools.studio_statistics(w.db,w.tray);assert stats['orders']==1 and stats['prepared_photos']==1 and stats['generated_copies']==0
        page.code.setText(tools.qr_payload(order['id']));page.lookup();assert manager.order_page.current_id==order['id']
        page.printer.setText('Test printer');page.save_calibration();assert 'Test printer' in w.db.get('printer_profiles')
    finally:w.close();app.processEvents()


def test_installer_configuration_preserves_data_and_default_locations():
    root=Path(__file__).resolve().parents[1];script=(root/'installer/Printora.iss').read_text()
    assert 'DefaultDirName=C:\\Printora' in script and 'PrivilegesRequired=admin' in script
    assert '{commondesktop}\\Printora' in script and '{commonprograms}\\Printora\\Printora' in script
    assert '[UninstallDelete]' not in script and 'AppMutex=Local\\Printora.Desktop.Running' in script
