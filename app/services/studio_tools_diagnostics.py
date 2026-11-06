"""Isolated source/frozen acceptance for the optional studio tools."""
def verify_tools(w,out,items,wait):
    from app.services import studio_tools as service
    from pypdf import PdfReader
    page=w.studio.tools;page.refresh()
    results=[];model=w.db.get('model_dir');root=w.db.path.parent
    w.run(lambda:service.batch_prepare(items[:2],{'quality':'fine','framing':'balanced'},model,root),results.extend);wait(w)
    assert len(results)==2 and all(r['job'] and not r['reviewed'] for r in results)
    page.prepared(results);page.save_reviewed();assert not any(r['saved'] for r in results)
    for index in range(len(results)):page.result_list.setCurrentRow(index);page.review()
    page.save_reviewed();assert all(r['saved'] for r in results)
    for r in results:assert w.db.load_job(r['job'].id).photos[0].provenance['library_ids']
    order=w.studio.orders.create(results[0]['job'],notes='Diagnostic note')
    qr=out/'order-qr.png';service.export_qr(order['id'],qr);assert service.decode_qr(qr)==order['id']
    service.receipt_pdf(order,results[0]['job'],out/'receipt.pdf',amount='120',currency='BDT')
    assert '120.00' in PdfReader(out/'receipt.pdf').pages[0].extract_text()
    service.contact_sheet(items,out/'contact-sheet.pdf',include_names=False)
    assert len(PdfReader(out/'contact-sheet.pdf').pages)>0
    service.calibration_sheet(out/'calibration.pdf');page.printer.setText('Diagnostic printer');page.save_calibration()
    assert 'Diagnostic printer' in w.db.get('printer_profiles')
    stats=service.studio_statistics(w.db,w.tray);assert stats['orders']>0 and stats['prepared_photos']==len(w.tray.items)
    w.studio.show(page);page.tabs.setCurrentIndex(3);w.grab().save(str(out/'studio-statistics.png'))
    page.tabs.setCurrentIndex(0);page.result_list.setCurrentRow(0);w.grab().save(str(out/'batch-review.png'))
    return ['batch fine-edge preparation','explicit per-item review and durable jobs','local order QR roundtrip','optional receipt pricing','serial contact sheets','exact calibration reference and saved measurements','local studio statistics']
