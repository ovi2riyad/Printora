"""Installed-driver printing from authoritative ReportLab PDFs, in an isolated process."""
from pathlib import Path
import json
import os
import subprocess
from PySide6.QtCore import QSize, QSizeF, QRectF, QPointF, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QImage
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtPdf import QPdfDocument
from app.models.domain import Job
from app.services.hardware import PrintableArea, preflight_print, page_pixels
from app.services.layout import page_size


def enumerate_printers():
    # A spooler queue is not proof that a physical device is connected or has paper.
    statuses = {}
    if os.name == 'nt':
        command = ('Get-CimInstance Win32_Printer | Select-Object Name,Default,WorkOffline,PrinterStatus,DetectedErrorState '
                   '| ConvertTo-Json -Compress')
        command='[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); '+command
        result = subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),
                                 '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0 and result.stdout.strip():
            rows = json.loads(result.stdout.decode('utf-8-sig'))
            for row in rows if isinstance(rows, list) else [rows]:
                statuses[row['Name']] = row
    printers = []
    for info in QPrinterInfo.availablePrinters():
        row = statuses.get(info.printerName(), {})
        status = ('Offline' if row.get('WorkOffline') or row.get('PrinterStatus') == 7 else
                  'Busy' if row.get('PrinterStatus') == 4 else
                  'Error' if row.get('PrinterStatus') in (6, 9) else
                  'Ready' if row.get('PrinterStatus')==3 and row.get('DetectedErrorState')==2 and row.get('WorkOffline') is False else
                  'Queue available; physical readiness unverified')
        printers.append(dict(id=info.printerName(), name=info.printerName(), default=info.isDefault(),
                             status=status, papers=[p.name() for p in info.supportedPageSizes()],
                             paper_sizes=[dict(name=p.name(),mm=[p.size(QPageSize.Millimeter).width(),p.size(QPageSize.Millimeter).height()]) for p in info.supportedPageSizes()],resolutions=info.supportedResolutions(),custom_paper=info.supportsCustomPageSizes()))
    return dict(printers=printers)


def configured_printer(name, landscape,paper_mm=None):
    info = QPrinterInfo.printerInfo(name)
    if info.isNull():
        raise ValueError('Printer not found. Refresh devices and choose an installed printer.')
    if paper_mm:
        requested=QPageSize(QSizeF(*paper_mm),QPageSize.Millimeter)
        if not any(abs(p.size(QPageSize.Millimeter).width()-paper_mm[0])<.5 and abs(p.size(QPageSize.Millimeter).height()-paper_mm[1])<.5 for p in info.supportedPageSizes()) and not info.supportsCustomPageSizes():raise ValueError('This printer does not report support for the selected paper')
    else:
        requested=QPageSize(QPageSize.A4)
        if not any(p.id() == QPageSize.A4 for p in info.supportedPageSizes()):raise ValueError('This printer does not report A4 support')
    printer = QPrinter(info, QPrinter.HighResolution)
    printer.setCopyCount(1)  # Photo copies are already present in the PDF.
    printer.setDuplex(QPrinter.DuplexNone)
    printer.setPageSize(requested)
    printer.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    full = printer.pageLayout().fullRect(QPageLayout.Millimeter)
    expected = tuple(reversed(paper_mm)) if paper_mm and landscape else tuple(paper_mm) if paper_mm else (297,210) if landscape else (210,297)
    if abs(full.width()-expected[0]) > .2 or abs(full.height()-expected[1]) > .2:
        raise ValueError('Printer driver did not accept the requested A4 orientation')
    # Capture the hardware limits BEFORE setFullPage changes the paint origin.
    layout = printer.pageLayout()
    layout.setUnits(QPageLayout.Millimeter)
    margins = layout.minimumMargins()
    area = PrintableArea(margins.left(), margins.top(), expected[0]-margins.right(), expected[1]-margins.bottom())
    return printer, area


def printer_capabilities(name, landscape,paper_mm=None):
    printer, area = configured_printer(name, landscape,paper_mm) if paper_mm else configured_printer(name,landscape)
    return dict(area=vars(area), resolution=printer.resolution(), printer=name,
                paper='A4', landscape=landscape)


def print_pdf(printer, path, job, ledger=None):
    """Rasterize one full PDF page at a time; never fit to the printable rectangle."""
    document = QPdfDocument()
    if document.load(str(path)) != QPdfDocument.Error.None_:
        raise ValueError('Print PDF could not be opened')
    if document.pageCount() != job.page_count:
        raise ValueError('PDF page count differs from the reviewed job')
    width, height = page_size(job.print_settings)
    for index in range(document.pageCount()):
        points = document.pagePointSize(index)
        if abs(points.width()*25.4/72-width) > .01 or abs(points.height()*25.4/72-height) > .01:
            raise ValueError('PDF paper differs from the reviewed A4 layout')
    printer.setFullPage(True)
    printer.setCopyCount(1)
    printer.setDocName('Printora — Actual Size 100%')
    if ledger:
        ledger('submitting; physical output unknown')
    painter = QPainter()
    if not painter.begin(printer):
        raise ValueError('Driver rejected the print job; no automatic retry was made')
    try:
        for index in range(document.pageCount()):
            if index and not printer.newPage():
                raise ValueError('Driver rejected a subsequent page; output may be partial')
            image = document.render(index, QSize(*page_pixels(width, height)))
            if image.isNull():
                raise ValueError('PDF page rendering failed; output may be partial')
            opaque=QImage(image.size(),QImage.Format_RGB32);opaque.fill(Qt.white)
            compositor=QPainter(opaque);compositor.drawImage(QPointF(0,0),image);compositor.end()
            image=opaque
            # QPrinter logical units are printer pixels, origin is physical paper top-left.
            rect = QRectF(0, 0, width/25.4*printer.resolution(), height/25.4*printer.resolution())
            painter.drawImage(rect, image)
            del image
    except Exception:
        printer.abort()
        raise
    finally:
        ended = painter.end()
        document.close()
    if not ended or printer.printerState() in (QPrinter.Error, QPrinter.Aborted):
        raise ValueError('Driver did not confirm submission; physical output may be partial')
    if ledger:
        ledger('submitted to driver; physical output unconfirmed')
    return dict(pages=job.page_count, status='Submitted to driver; physical output unconfirmed')


def dispatch(request):
    action = request['action']
    if action == 'inspect_scans':
        from app.services.hardware import inspect_scans
        return inspect_scans(request['folder'],request['pages'],request['provenance'])
    if action == 'inspect_scan':
        from app.services.hardware import inspect_scan
        return inspect_scan(request['path'], request['folder'], request['provenance'])
    if action == 'printers':
        return enumerate_printers()
    if action == 'printer_caps':
        return printer_capabilities(request['printer'], request['landscape'],request.get('paper_mm'))
    if action == 'properties':
        # Native PrintUI properties opens independently; no shell command interpolation.
        if QPrinterInfo.printerInfo(request['printer']).isNull():
            raise ValueError('Printer no longer installed')
        executable = str(Path(os.environ['SystemRoot'])/'System32/rundll32.exe')
        subprocess.Popen([executable, 'printui.dll,PrintUIEntry', '/p', '/n', request['printer']])
        return dict(status='Printer properties opened')
    if action == 'print':
        job = Job.from_dict(request['job'])
        args=(request['printer'],job.print_settings.get('landscape',False))
        printer, area = configured_printer(*args,job.print_settings['document_paper_mm']) if job.print_settings.get('policy')=='document' else configured_printer(*args)
        status = next((p for p in enumerate_printers()['printers'] if p['id'] == request['printer']), None)
        if not status or status['status'] in ('Offline', 'Error'):
            raise ValueError('Printer is unavailable; no print was submitted')
        automatic=request.get('automatic',False)
        if type(automatic) is not bool or automatic and status['status']!='Ready':raise ValueError('Automatic submission stopped: printer readiness is unverified')
        preflight_print(job, area)
        folder = Path(request['folder']).resolve()
        if folder.parent.name != 'print-spool' or not folder.is_dir():
            raise ValueError('Invalid print transaction folder')
        def ledger(state):
            payload = dict(token=folder.name, printer=request['printer'], status=state)
            temporary = folder/'status.tmp'
            temporary.write_text(json.dumps(payload), encoding='utf-8')
            temporary.replace(folder/'status.json')
        if (folder/'status.json').exists():
            raise ValueError('This print transaction was already attempted. Review the queue before creating another request.')
        from app.services.print_transactions import unresolved
        if unresolved(folder.parent.parent):raise ValueError('OutcomeUnknown: check and acknowledge previous submissions before printing')
        color=request.get('color','color')
        if color not in ('color','gray'):raise ValueError('Unsupported printer color mode')
        printer.setColorMode(QPrinter.GrayScale if color=='gray' else QPrinter.Color)
        import re
        name=request.get('pdf_name','sheet.pdf')
        if not isinstance(name,str) or not re.fullmatch(r'sheet(?:-[0-9a-f]{32})?\.pdf',name):raise ValueError('Invalid reviewed PDF revision')
        path=folder/name
        if path.is_symlink() or path.resolve().parent!=folder:raise ValueError('Invalid reviewed PDF path')
        return print_pdf(printer, path, job, ledger)
    raise ValueError('Unknown printer operation')


def helper_main():
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(['Printora device worker'])
    position=sys.argv.index('--hardware-worker')
    request_path=Path(sys.argv[position+1]); result_path=Path(sys.argv[position+2])
    if result_path.parent!=request_path.parent or result_path.exists():
        return 2
    try:
        with request_path.open('rb') as stream:raw=stream.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError('Hardware request too large')
        result = dispatch(json.loads(raw.decode('utf-8')))
        payload=dict(ok=True,result=result);code=0
    except Exception as error:
        payload=dict(ok=False,error=str(error));code=1
    with result_path.open('x',encoding='utf-8') as stream:json.dump(payload,stream)
    return code
