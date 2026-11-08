"""Integrated scan review and explicit 100% print submission. All driver calls are isolated."""
from pathlib import Path
import copy
import json
import os
import sys
import uuid
from PySide6.QtCore import QObject, Qt, QUrl,Signal
from PySide6.QtGui import QDesktopServices,QColor
from PySide6.QtWidgets import (QWidget, QFrame, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox,QSpinBox, QDoubleSpinBox, QGroupBox, QMessageBox, QScrollArea,QProgressBar,QCheckBox,QGridLayout,QApplication,QInputDialog,QSizePolicy,QGraphicsView)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from app.core.database import data_root
from app.services.hardware import (ScannerManager, HARDWARE_DEFAULTS, new_scan_folder,
                                  check_scan_request, PrintableArea, preflight_print,direct_print_quality)
from app.services.layout import validate_layout,auto_layout
from app.ui.hardware_process import HardwareProcess
from app.ui.cropper import CropCanvas,Corner

class ScanAreaCanvas(CropCanvas):
    minimum_draw_pixels=2
    def mousePressEvent(self,event):
        # In Scan Studio a drag selects a NEW area, even inside the old rectangle.
        # Handles still resize the existing area; Pan remains an explicit tool.
        if event.button()==Qt.LeftButton and not getattr(self,'pan_mode',False):
            self.draw_mode=not isinstance(self.itemAt(event.position().toPoint()),Corner)
        super().mousePressEvent(event)

    def display(self,image,regions,selected=0):
        super().display(image,regions,selected)
        for outline in self.outlines:
            outline.rectangular=True
            # Scanner regions use continuous image edges, including W/H.
            outline.bounds=(image.width+1,image.height+1)


def text_label(text):
    widget = QLabel(text); widget.setWordWrap(True); return widget


class HardwareHub(QObject):
    """Owns process lifetime independently of the active editor/document generation."""
    def __init__(self, window):
        super().__init__(window)
        self.w = window; self.scanner_manager = ScannerManager()
        self.scanners = []; self.printers = []; self.scan_dialog = None; self.print_dialog = None
        self.scan_process = HardwareProcess(self); self.printer_process = HardwareProcess(self);self.twain_process=HardwareProcess(self)
        self.twain_process.succeeded.connect(self.twain_devices);self.twain_process.failed.connect(self.twain_error)
        self.verified_backends=set();self.fallback_attempts=0;self.fallback_tried=set();self.fallback_running=False;self.fallback_errors=[]
        self.scan_action = None; self.scan_request = None; self.printing = False
        self.scan_process.succeeded.connect(self.scanner_result)
        self.scan_process.failed.connect(self.scanner_error)
        self.printer_process.succeeded.connect(self.printer_result)
        self.printer_process.failed.connect(self.printer_error)
        self.panel = QFrame(); self.panel.setObjectName('card'); outer = QVBoxLayout(self.panel)
        heading = QLabel('Scan & Print'); heading.setStyleSheet('font-size:21px;font-weight:600'); outer.addWidget(heading)
        form = QFormLayout(); self.scanner = QComboBox(); self.printer = QComboBox()
        form.addRow('Scanner', self.scanner); form.addRow('Printer', self.printer); outer.addLayout(form)
        self.status = text_label('Checking devices happens separately from editing. No device has been checked yet.')
        outer.addWidget(self.status); row = QHBoxLayout(); outer.addLayout(row)
        for title, fn in [('Scan Photos', lambda:self.open_scan(False)), ('Scan & Edit', lambda:self.open_scan(True)),
                          ('Quick Print', self.quick_print), ('Refresh Devices', self.refresh)]:
            button = QPushButton(title); button.clicked.connect(fn); row.addWidget(button)
        self.scanner.addItem('Not checked', None); self.printer.addItem('Not checked', None)
        self.scanner.activated.connect(self.select_scanner); self.printer.activated.connect(self.select_printer)

    def remember(self, key, value):
        from app.services.hardware import validate_hardware_setting
        self.w.db.set(key, validate_hardware_setting(key, value))

    def refresh(self):
        started = []
        if not self.scan_process.active:
            self.scan_action = 'devices'
            try:
                self.scan_process.start('wia', self.scanner_manager.request('devices'), 15000)
                started.append('scanners')
            except ValueError as error:
                self.scanner_error(str(error))
        if not self.printer_process.active:
            self.printer_process.start('printer', dict(action='printers'), 25000); started.append('printers')
        if not self.twain_process.active:self.twain_process.start('twain32',dict(action='devices'),20000)
        self.status.setText('Refreshing '+', '.join(started)+'…' if started else 'Busy. Wait for the current device operation.')

    def populate(self, box, rows, preferred, empty):
        previous = box.currentData(); box.blockSignals(True); box.clear()
        for row in rows:
            box.addItem(row['name']+(' (Windows default)' if row.get('default') else ''), row['id'])
        if not rows:
            box.addItem(empty, None)
        else:
            selected = preferred or previous
            index = box.findData(selected)
            if index < 0:
                index = next((i for i, row in enumerate(rows) if row.get('default')), 0)
            box.setCurrentIndex(index)
        box.blockSignals(False)

    def scanner_result(self, result):
        action = self.scan_action
        if action == 'devices':
            self.scanners = result['devices']+[d for d in self.scanners if d.get('backend')=='twain32']
            self.populate(self.scanner, self.scanners, self.w.db.get('scanner_id',''), 'Not Found — refresh after connecting a scanner')
            if self.scan_dialog:
                self.scan_dialog.update_devices()
            self.update_status()
            if self.scan_dialog and self.scan_dialog.pending_scan and not self.scanners and not self.twain_process.active:self.scan_dialog.error('No available scanner interface was found. Check the connection and installed driver.')
        elif self.scan_dialog:
            self.scan_dialog.result(action, result)
    def twain_devices(self,result):
        # WIA and TWAIN have different identifiers; show backend suffix rather than
        # guessing identities or silently combining two physical devices.
        self.scanners=[d for d in self.scanners if d.get('backend')!='twain32']+result['devices']
        self.populate(self.scanner,self.scanners,self.w.db.get('scanner_id',''),'No scanner')
        if self.scan_dialog and not self.scan_process.active:self.scan_dialog.update_devices()
        self.update_status()
        if self.scan_dialog and self.scan_dialog.pending_scan and not self.scanners and not self.scan_process.active:self.scan_dialog.error('No available scanner interface was found. Check the connection and installed driver.')

    def twain_error(self,error):
        self.status.setToolTip('TWAIN: '+error)
        if self.scan_dialog and self.scan_dialog.pending_scan and not self.scan_process.active:
            if self.scanners:self.scan_dialog.update_devices()
            else:self.scan_dialog.error('Scanner discovery failed: '+error)

    def scanner_error(self, error):
        dialog=self.scan_dialog
        if dialog and self.scan_action in ('scan','capabilities'):
            from app.services.hardware import fallback_candidates
            current_id=dialog.device.currentData()
            self.fallback_tried.add(current_id);self.fallback_errors.append(dialog.device.currentText()+': '+error)
            started=self.scan_action=='scan' and bool(dialog.folder and (dialog.folder/'acquisition.started').exists())
            canceled=getattr(dialog,'user_canceled',False) or (self.scan_action=='scan' and bool(dialog.folder and (dialog.folder/'cancel.request').exists()))
            candidates=fallback_candidates(self.scanners,current_id,self.fallback_tried,self.w.db.get('scanner_fallbacks',{}))
            if not started and not canceled and candidates and self.fallback_attempts<max(0,len(self.scanners)-1):
                alternate=candidates[0];self.fallback_attempts+=1;self.fallback_running=True
                if self.scan_action=='scan':
                    dialog.retry_request=dict(self.scan_request);dialog.pending_scan=True
                    if dialog.acquisition_preview:dialog.preview_pending=True
                self.populate(dialog.device,self.scanners,alternate['id'],'No scanner');dialog.device_changed()
                dialog.connect_device();dialog.message.setText('Trying '+alternate['name']+' automatically ('+str(self.fallback_attempts+1)+'/'+str(len(self.scanners))+').');return
            self.fallback_running=False
            if len(self.fallback_errors)>1:error+='\nTried: '+'; '.join(self.fallback_errors)
        elif dialog and self.scan_action=='devices' and dialog.pending_scan:
            if self.scanners:dialog.update_devices();return
            if self.twain_process.active:self.status.setText('WIA unavailable; waiting for other scanner interfaces.');return
        self.status.setText('Scanner Error / Driver Unavailable: '+error)
        if self.scan_dialog:
            self.scan_dialog.error(error)

    def printer_result(self, result):
        self.printers = result['printers']
        self.populate(self.printer, self.printers, self.w.db.get('preferred_printer',''), 'Not Found — install a Windows printer driver')
        self.update_status()
        if self.print_dialog:
            self.print_dialog.update_devices()
        if hasattr(self.w,'shell'):
            self.w.shell.copy.update_printers();self.w.shell.nid.update_printers();self.w.shell.active()

    def printer_error(self, error):
        self.status.setText('Printer Error / Driver Unavailable: '+error)

    def update_status(self):
        scanner = next((d for d in self.scanners if d['id'] == self.scanner.currentData()), None)
        printer = next((d for d in self.printers if d['id'] == self.printer.currentData()), None)
        self.status.setText('Scanner: '+(scanner['status'] if scanner else 'Not Found')+
                            '\nPrinter: '+(printer['status'] if printer else 'Not Found'))
        if hasattr(self.w,'shell'):
            self.w.shell.copy.update_printers();self.w.shell.nid.update_printers();self.w.shell.active()

    def select_scanner(self, *_):
        if self.scanner.currentData():
            self.remember('scanner_id', self.scanner.currentData())
        self.update_status()
        if self.scan_dialog:
            self.scan_dialog.update_devices()

    def select_printer(self, *_):
        if self.printer.currentData():
            self.remember('preferred_printer', self.printer.currentData())
        self.update_status()

    def open_scan(self, edit=False):
        if self.w.busy or not self.w.save_before_leave():
            return
        if self.scan_dialog is None:
            self.scan_dialog = ScanDialog(self)
        self.scan_dialog.purpose.setText('Preview → drag the area → Scan Now → review in Cropper → Portrait / Joint.' if edit else
                                       '1. Preview the bed   2. Drag the area you want   3. Scan Now. Choose A4, Letter or a saved area for repeat work.')
        if self.w.stack.indexOf(self.scan_dialog)>=0:self.w.stack.setCurrentWidget(self.scan_dialog)
        self.scan_dialog.show(); self.scan_dialog.raise_()
        if not self.scanners and not self.scan_process.active:
            self.refresh()
        elif self.scanners and not self.scan_dialog.sources and not self.scan_process.active:self.scan_dialog.connect_device()

    def quick_print(self):
        # Do not create a new unsafe saved-document load route (PA-010).
        if self.w.stack.currentWidget() is self.w.studio.multi:
            self.print_job(self.w.studio.multi.job); return
        if self.w.photo and self.w.photo.layers:
            self.print_job(self.w.job); return
        QMessageBox.information(self.w, 'Choose a reviewed composition',
            'Prepare a Portrait / Joint photo or open a Multi Photo Print session, then choose Print. '
            'Raw library images need review before printing.')
        self.w.studio.show(self.w.studio.multi)

    def print_job(self, job,auto=False,direct=False,driver_color=None,printer_id=None):
        if self.w.busy:
            return False
        if self.printing:
            QMessageBox.information(self.w, 'Print request in progress', 'Review the current print request before starting another.'); return False
        try:
            snapshot = copy.deepcopy(job)
            from app.services.record_recovery import checked_document
            checked_document(snapshot)
            if not job.photos or not any(p.layers for p in job.photos):
                raise ValueError('Prepare and arrange a composition before printing')
            if not snapshot.placements:
                if snapshot.print_settings.get('auto_orientation'):
                    from app.services.print_sessions import choose_orientation
                    snapshot.print_settings,snapshot.placements,snapshot.page_count=choose_orientation(snapshot.photos,snapshot.print_settings)
                else:
                    snapshot.placements=auto_layout(snapshot.photos,snapshot.print_settings)
                    snapshot.page_count=max(p.page for p in snapshot.placements)+1
            validate_layout(snapshot)
        except (ValueError, TypeError, AttributeError) as error:
            QMessageBox.warning(self.w, 'Review print layout', str(error)); return False
        if self.print_dialog:
            if self.print_dialog.process.active and self.print_dialog.action=='print':return False
            self.print_dialog.process.shutdown();self.print_dialog.document.close();self.print_dialog.close()
        folder = data_root()/'print-spool'/uuid.uuid4().hex; folder.mkdir(parents=True, exist_ok=False)
        self.printing = True
        self.w.notify('Preparing print PDF…')
        from app.services.pdf import export_pdf
        def failed(error):
            self.printing = False
            self.w.notify('Print PDF could not be prepared: '+str(error))
        def prepare():
            warnings=direct_print_quality(snapshot)
            export_pdf(snapshot,folder/'sheet.pdf',dpi=int(snapshot.print_settings.get('dpi',300)))
            return warnings
        def ready(warnings):
            self.printing = False
            self.print_dialog = PrintDialog(self, snapshot, folder,warnings,printer_id=printer_id)
            self.print_dialog.direct_requested=bool(direct)
            if driver_color in ('color','gray'):self.print_dialog.color.setCurrentIndex(self.print_dialog.color.findData(driver_color))
            from app.services.print_transactions import profile_key
            printer=self.printer.currentData()
            known=profile_key(snapshot,self.w.db.get('preferred_print_color','color')) in self.w.db.get('confirmed_print_profiles',{}).get(printer,[])
            self.print_dialog.auto_requested=bool(direct or auto or self.w.db.get('quick_print',False) and known)
            if not self.print_dialog.auto_requested:self.print_dialog.show()
            if not self.printers and not self.printer_process.active:
                self.refresh()
        # Export a copied document; the worker callback never adopts or saves an editor job.
        if snapshot.print_settings.get('policy')=='document':
            def prepare_document():
                export_pdf(snapshot,folder/'sheet.pdf',dpi=int(snapshot.print_settings.get('dpi',300)));return []
            self.w.run(prepare_document,ready,failed)
        else:self.w.run(prepare,ready,failed)
        return True

    def operation_active(self):
        return ((self.scan_process.active and self.scan_action == 'scan') or self.printing or
                bool(self.scan_dialog and self.scan_dialog.verifier.active))

    def shutdown(self):
        self.scan_process.shutdown(); self.printer_process.shutdown();self.twain_process.shutdown()
        if self.scan_dialog:
            self.scan_dialog.verifier.shutdown()
        if self.print_dialog:
            self.print_dialog.process.shutdown()


class ScanDialog(QDialog):
    def __init__(self, hub):
        super().__init__(hub.w); self.hub = hub; self.sources = []; self.folder = None; self.completed = None
        self.pending_scan=False;self.preview_pending=False;self.completion_callback=None;self.completion_owner=None;self.folder_root=None;self.capability_time=0;self.retry_request=None
        self.area_context=None;self.preview_context=None;self.acquisition_preview=False
        self.request_overrides=None
        self.setWindowTitle('Printora — Scan & review'); self.resize(900,750)
        self.verifier = HardwareProcess(self); self.verifier.succeeded.connect(self.verified); self.verifier.failed.connect(self.error)
        outer = QVBoxLayout(self); self.purpose = text_label('1. Preview   2. Drag an area   3. Scan Now. Save named areas for repeat work.'); outer.addWidget(self.purpose)
        settings=QWidget();form = QFormLayout(settings)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(settings);scroll.setMinimumHeight(220);scroll.setMaximumHeight(370);outer.addWidget(scroll)
        settings_toggle=QPushButton('Scanner settings');self.settings_toggle=settings_toggle;settings_toggle.setCheckable(True);settings_toggle.toggled.connect(scroll.setVisible);outer.insertWidget(1,settings_toggle);scroll.hide()
        self.device = QComboBox(); form.addRow('Scanner', self.device)
        self.backend = QComboBox(); self.backend.addItem('Windows Image Acquisition (WIA)', 'wia');self.backend.addItem('Isolated TWAIN (32-bit)','twain32');self.backend.setEnabled(False); form.addRow('Backend', self.backend)
        self.backend.setToolTip('WIA is preferred. Installed 32-bit TWAIN sources run in an isolated matching-bitness helper. Acquisition remains hardware-unverified until a real scan succeeds.')
        self.source = QComboBox(); form.addRow('Driver scan source', self.source)
        self.feeder_pages=QSpinBox();self.feeder_pages.setRange(1,100);self.feeder_pages.setValue(1);self.feeder_label=QLabel('Feeder page limit (simplex)');form.addRow(self.feeder_label,self.feeder_pages);self.feeder_pages.hide();self.feeder_label.hide()
        self.dpi = QComboBox(); form.addRow('Resolution (DPI)', self.dpi)
        self.color = QComboBox(); form.addRow('Color mode', self.color)
        self.paper=QComboBox();self.paper.addItems(['Full bed','A4','Letter','Custom area']);self.paper.activated.connect(self.paper_changed);form.addRow('Scan area',self.paper)
        self.area_presets=QComboBox();self.area_presets.activated.connect(self.use_preset);form.addRow('Saved areas',self.area_presets)
        preset_actions=QWidget();preset_row=QHBoxLayout(preset_actions);preset_row.setContentsMargins(0,0,0,0)
        self.save_area_button=QPushButton('Save area…');self.save_area_button.clicked.connect(self.save_area);preset_row.addWidget(self.save_area_button)
        remove_area=QPushButton('Remove');remove_area.clicked.connect(self.remove_area);preset_row.addWidget(remove_area);self.remove_area_button=remove_area;form.addRow(preset_actions)
        advanced=QWidget();advanced_form=QFormLayout(advanced);advanced_form.setContentsMargins(0,0,0,0)
        self.region = []
        for title in ('Left (mm)','Top (mm)','Width (mm)','Height (mm)'):
            control = QDoubleSpinBox(); control.setRange(0,1000); control.setDecimals(3); advanced_form.addRow(title,control); self.region.append(control)
        self.area_summary=text_label('Preview, then drag over the area you want to scan.');form.addRow(self.area_summary)
        self.advanced_area=advanced;advanced_button=QPushButton('Advanced coordinates');advanced_button.setCheckable(True);advanced_button.toggled.connect(advanced.setVisible);form.addRow(advanced_button);form.addRow(advanced);advanced.hide()
        for box in self.region:box.valueChanged.connect(self.coordinates_changed)
        self.message = text_label('Choose a scanner and Connect / Read capabilities.'); outer.addWidget(self.message)
        self.scan_progress=QProgressBar();self.scan_progress.setRange(0,0);self.scan_progress.hide();outer.addWidget(self.scan_progress)
        self.preview = QLabel('The completed scan preview appears here.'); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(120); outer.addWidget(self.preview,1)
        self.preview.hide()
        from app.ui.cropper import CropCanvas
        self.preview_canvas=ScanAreaCanvas();self.preview_canvas.setMinimumSize(300,240);outer.addWidget(self.preview_canvas,1)
        bar=QHBoxLayout();outer.addLayout(bar)
        for title,fn in [('Full Bed',self.full_bed),('Draw Area',self.draw_area),('Auto Detect',self.detect_area),('Rotate view',lambda:self.preview_canvas.rotate(90)),('Fit',lambda:self.preview_canvas.fitInView(self.preview_canvas.sceneRect(),Qt.KeepAspectRatio)),('100%',self.preview_canvas.resetTransform),('＋',lambda:self.preview_canvas.scale(1.2,1.2)),('−',lambda:self.preview_canvas.scale(1/1.2,1/1.2)),('Pan',self.pan_preview)]:
            button=QPushButton(title);button.clicked.connect(fn);bar.addWidget(button)
        self.apply_area=__import__('PySide6.QtWidgets',fromlist=['QCheckBox']).QCheckBox('Use this rectangle as the next hardware scan region');outer.addWidget(self.apply_area)
        self.apply_area.toggled.connect(lambda checked:self.area_changed() if checked else None)
        self.apply_area.hide()
        self.preview_canvas.changed.connect(self.area_changed);self.preview_canvas.drawn.connect(self.area_drawn)
        self.preview_image=None;self.preview_acquired_region=None
        row = QHBoxLayout(); outer.addLayout(row)
        self.connect_button = QPushButton('Refresh capabilities'); self.connect_button.clicked.connect(self.connect_device);form.addRow(self.connect_button)
        fallback_button=QPushButton('Link verified fallback backend');fallback_button.clicked.connect(self.link_fallback);form.addRow(fallback_button)
        self.scan_button = QPushButton('Scan Now');self.scan_button.clicked.connect(self.scan_now)
        preview_button=QPushButton('Preview');self.preview_button=preview_button;preview_button.clicked.connect(lambda:self.scan_now(preview=True));row.addWidget(preview_button)
        row.addWidget(self.scan_button)
        self.cancel_button = QPushButton('Request cancel'); self.cancel_button.setEnabled(False); self.cancel_button.clicked.connect(self.cancel); row.addWidget(self.cancel_button)
        self.open_button = QPushButton('Open in Cropper'); self.open_button.setEnabled(False); self.open_button.clicked.connect(self.open_cropper); row.addWidget(self.open_button)
        edit_document=QPushButton('Edit / Copy document');edit_document.clicked.connect(self.edit_document);row.addWidget(edit_document)
        folder_button = QPushButton('Saved scans'); folder_button.clicked.connect(self.show_folder); row.addWidget(folder_button)
        self.device.activated.connect(self.device_changed); self.source.currentIndexChanged.connect(self.source_changed)
        # Keep acquisition settings beside the real preview, with one primary Scan action.
        settings_toggle.hide();scroll.setVisible(True);scroll.setMaximumHeight(16777215);scroll.setMinimumHeight(0);form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        outer.removeWidget(scroll);outer.removeWidget(self.preview_canvas);outer.removeWidget(self.message);outer.removeWidget(self.scan_progress);outer.removeWidget(self.apply_area);outer.removeItem(bar);outer.removeItem(row)
        from app.ui.panels import AdaptivePanel,splitter
        from app.ui.workflow_settings import WorkflowSettings,move_rows
        self.advanced_settings=WorkflowSettings(self,'Scan Studio');self.advanced_settings.add_widget(scroll)
        basic=QWidget();basic_form=QFormLayout(basic);basic_form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        move_rows(form,basic_form,[self.device,self.dpi]);self.basic_area=text_label('A4 · 210 × 297 mm');basic_form.addRow('Page',self.basic_area)
        self.advanced_button=QPushButton('Settings');self.advanced_button.clicked.connect(self.advanced_settings.open_settings);basic_form.addRow(self.advanced_button)
        body=QHBoxLayout();self.settings_panel=AdaptivePanel(basic,hub.w.db,'scan','Scan controls',default_width=290,minimum_width=250);right=QVBoxLayout();right.addWidget(self.preview_canvas,1)
        tools=QGridLayout()
        i=0
        while bar.count():
            item=bar.takeAt(0)
            if item.widget():tools.addWidget(item.widget(),i//5,i%5);i+=1
        self.advanced_settings.add_layout(tools);self.advanced_settings.add_widget(self.apply_area);right.addWidget(self.message);right.addWidget(self.scan_progress);preview_area=QWidget();preview_area.setLayout(right);body.addWidget(splitter(self.settings_panel,preview_area));outer.addLayout(body,1)
        actions=QGridLayout();i=0
        while row.count():
            item=row.takeAt(0)
            if item.widget():
                if item.widget() in (edit_document,folder_button):self.advanced_settings.add_widget(item.widget())
                else:actions.addWidget(item.widget(),i//4,i%4);i+=1
        self.scan_button.setObjectName('primary');outer.addLayout(actions)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for combo in (self.device,self.backend,self.source,self.dpi,self.color,self.paper,self.area_presets):
            combo.setMinimumContentsLength(12);combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);combo.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.clear_preview();self.update_devices()

    def update_devices(self):
        if self.hub.scan_process.active and self.hub.scan_action == 'scan':
            return
        self.hub.populate(self.device, self.hub.scanners, self.hub.scanner.currentData(), 'Not Found — Refresh Devices on dashboard')
        self.device_changed()
        if self.pending_scan and self.device.currentData():self.connect_device()

    def device_changed(self, *_):
        if self.sources and self.area_context and self.area_context[0]==self.device.currentData():return
        if self.area_context and self.area_context[0]!=self.device.currentData():self.clear_preview();self.area_context=None
        self.backend.setCurrentIndex(max(0,self.backend.findData(self.backend_kind())))
        self.sources=[]; self.source.clear(); self.dpi.clear(); self.color.clear(); self.scan_button.setEnabled(True)
        if self.device.currentData():
            self.message.setText('Detected; Connect to check availability. This is not yet a readiness check.')

    def connect_device(self):
        if self.hub.scan_process.active:
            self.error('Busy. Wait for the current scanner operation.'); return
        if not self.device.currentData():
            self.error('Scanner Not Found. Refresh devices after connecting it.'); return
        if not self.pending_scan and not self.hub.fallback_running:
            self.hub.fallback_tried=set();self.hub.fallback_attempts=0;self.hub.fallback_errors=[];self.user_canceled=False
        self.hub.scan_action='capabilities'; self.message.setText('Reading scanner capabilities… Preview will acquire a low-resolution bed image when requested.')
        self.scan_progress.show()
        self.scan_button.setEnabled(False)
        self.hub.scan_process.start(self.backend_kind(), self.hub.scanner_manager.request('capabilities', device=self.device.currentData()), 20000)
    def backend_kind(self):return 'twain32' if str(self.device.currentData()).startswith('twain32:') else 'wia'
    def edit_document(self):
        if not self.completed:self.message.setText('Complete and verify a scan first.');return
        if hasattr(self.hub.w,'shell'):
            shell=self.hub.w.shell;shell.open(shell.copy)
            if self.hub.w.stack.currentWidget() is shell.copy:shell.copy.import_scans(self.completed.get('pages') or [self.completed])

    def result(self, action, result):
        if action == 'capabilities':
            previous_context=self.area_context;previous_region=[box.value() for box in self.region];previous_dpi=self.dpi.currentData();previous_color=self.color.currentData();previous_source=self.source.currentData()
            self.scan_progress.hide()
            self.sources=result.get('sources',[]); self.source.blockSignals(True); self.source.clear()
            for item in self.sources:
                self.source.addItem(item['name'], item['id'])
            self.source.blockSignals(False)
            if not self.sources:self.hub.scanner_error('The scanner exposes no usable scan source.');return
            self.hub.fallback_running=False
            selected=self.source.findData(previous_source or self.hub.w.db.get('scan_source',''))
            if selected>=0:self.source.setCurrentIndex(selected)
            self.source_changed(); self.message.setText(result['status']+'. Click Preview, drag an area on the image, then Scan Now.')
            if previous_context==self.area_context and previous_dpi in self.sources[self.source.currentIndex()]['resolutions'] and previous_color in self.sources[self.source.currentIndex()]['colors']:
                try:
                    caps=self.sources[self.source.currentIndex()];check_scan_request(caps,previous_dpi,previous_color,previous_region)
                    self.dpi.setCurrentIndex(self.dpi.findData(previous_dpi));self.color.setCurrentIndex(self.color.findData(previous_color));self.set_region(previous_region)
                except ValueError:pass
            import time
            self.capability_time=time.monotonic()
            if self.pending_scan:
                # Preview is a full-bed, minimum-resolution request, rather than
                # the user's final scan resolution/ROI. Use the alternate bed's
                # own preview capability and retain the final DPI control.
                if self.preview_pending:self.retry_request=None
                if self.retry_request:
                    retry=self.retry_request;self.retry_request=None
                    try:check_scan_request(self.sources[self.source.currentIndex()],retry['dpi'],retry['color'],retry['region'])
                    except ValueError as error:self.retry_request=retry;self.hub.scanner_error('This scanner cannot preserve the requested area/DPI/color: '+str(error));return
                    if retry.get('max_pages',1)>1 and not self.sources[self.source.currentIndex()].get('batch'):self.retry_request=retry;self.hub.scanner_error('This scanner does not support the requested feeder batch.');return
                    self.feeder_pages.setValue(retry.get('max_pages',1))
                    self.dpi.setCurrentIndex(self.dpi.findData(retry['dpi']));self.color.setCurrentIndex(self.color.findData(retry['color']))
                    for box,value in zip(self.region,retry['region']):box.setValue(value)
                self.pending_scan=False;self.scan()
        elif action == 'scan':
            self.message.setText('Acquisition finished. Verifying the preserved original…')
            self.verifier.start('printer', dict(action='inspect_scans' if result.get('pages') else 'inspect_scan',pages=result.get('pages'), path=result['path'], folder=str(self.folder),
                provenance=dict(backend=self.backend_kind(), scanner_id=self.hub.scan_request['device'],
                    scanner_name=self.device.currentText(), settings=self.hub.scan_request, driver=result)), 60000)

    def source_changed(self, *_):
        i=self.source.currentIndex()
        if not 0 <= i < len(self.sources):
            self.scan_button.setEnabled(False); return
        caps=self.sources[i];context=(self.device.currentData(),caps['id'])
        if self.area_context!=context:self.clear_preview()
        self.area_context=context
        caps=self.sources[i]; self.dpi.clear(); self.color.clear();self.feeder_pages.setVisible(bool(caps.get('batch')));self.feeder_label.setVisible(bool(caps.get('batch')))
        if not caps.get('batch'):self.feeder_pages.setValue(1)
        for dpi in caps['resolutions']:self.dpi.addItem(str(dpi),dpi)
        preferred=self.hub.w.db.get('scan_dpi',300); index=self.dpi.findData(preferred)
        self.dpi.setCurrentIndex(index if index>=0 else 0)
        for color in caps['colors']:self.color.addItem('Color' if color=='color' else 'Grayscale',color)
        self.color.setCurrentIndex(max(0,self.color.findData(self.hub.w.db.get('scan_color','color'))))
        for control, value in zip(self.region,(0,0,caps['width_mm'],caps['height_mm'])):control.setValue(value)
        saved=self.hub.w.db.get('scan_region',[])
        if not saved and caps['width_mm']>=209.9 and caps['height_mm']>=296.9:saved=[0,0,min(210,caps['width_mm']),min(297,caps['height_mm'])]
        if saved:
            try:
                check_scan_request(caps,self.dpi.currentData(),self.color.currentData(),saved)
                for control,value in zip(self.region,saved):control.setValue(value)
            except ValueError:pass
        self.scan_button.setEnabled(bool(caps['resolutions'] and caps['colors']))
        self.refresh_area_presets();self.coordinates_changed()

    def scan(self):
        if self.hub.scan_process.active or self.verifier.active:
            self.error('Busy. Another scan has not finished.'); return
        try:
            caps=self.sources[self.source.currentIndex()]; region=[c.value() for c in self.region]
            overrides=self.request_overrides or {}
            preview=self.preview_pending;self.preview_pending=False
            self.acquisition_preview=preview
            selected_region=list(region)
            if overrides and not preview:
                region=[0,0,210.,297.]
                if caps['width_mm']>=209.9 and caps['height_mm']>=296.9:region=[0,0,min(210,caps['width_mm']),min(297,caps['height_mm'])]
            if preview:region=[0,0,caps['width_mm'],caps['height_mm']]
            dpi=min(caps['resolutions']) if preview else overrides.get('dpi',self.dpi.currentData()); color=overrides.get('color',self.color.currentData()); check_scan_request(caps,dpi,color,region)
            from app.services.user_folders import folder
            self.folder=new_scan_folder(self.folder_root) if self.folder_root else new_scan_folder(folder(self.hub.w.db,'scans'),direct=True); self.completed=None; self.open_button.setEnabled(False)
            request=self.hub.scanner_manager.request('scan',device=self.device.currentData(),item=caps['id'],dpi=dpi,
                color=color,region=region,folder=str(self.folder),cancel=str(self.folder/'cancel.request'),max_pages=self.feeder_pages.value() if caps.get('batch') and getattr(self.completion_owner,'kind',None)!='nid' else 1)
            if not overrides:
                for key,value in dict(scanner_id=request['device'],scanner_backend=self.backend_kind(),scan_source=caps['id'],scan_dpi=self.dpi.currentData() if preview else dpi,scan_color=color,scan_region=selected_region if preview else region).items():self.hub.remember(key,value)
            self.request_overrides=None
            self.hub.scan_request=request; self.hub.scan_action='scan'
            self.set_scanning(True); self.message.setText(('Acquiring full-bed preview…' if preview else 'Scanning selected area…')+' Cancel is a request; the driver may finish before it can be honored.')
            self.hub.scan_process.start(self.backend_kind(),request,240000)
        except (ValueError,IndexError,OSError) as error:self.error(str(error))

    def set_scanning(self, active):
        self.scan_progress.setVisible(active)
        self.cancel_button.setEnabled(active)
        for control in (self.device,self.source,self.dpi,self.color,self.connect_button,self.preview_button,self.paper,self.area_presets,self.save_area_button,self.remove_area_button,self.preview_canvas,*self.region):control.setEnabled(not active)
        self.scan_button.setEnabled(not active and bool(self.sources))

    def cancel(self):
        self.user_canceled=True
        self.hub.fallback_running=False
        if self.pending_scan:
            self.pending_scan=False;self.preview_pending=False;self.retry_request=None
            self.request_overrides=None
            if self.completion_owner and hasattr(self.completion_owner,'scan_failed'):self.completion_owner.scan_failed('Canceled before acquisition')
            if self.completion_owner:self.completion_owner.message.setText('Canceled before acquisition. No scan was started.')
            self.completion_callback=None;self.completion_owner=None;self.folder_root=None;self.cancel_button.setEnabled(False);self.message.setText('Canceled before acquisition.');return
        if self.hub.scan_process.active and self.hub.scan_action=='scan' and self.folder:
            (self.folder/'cancel.request').touch(exist_ok=True)
            self.message.setText('Cancel requested. Waiting for the driver; a completed transfer will be retained. No retry will run automatically.')

    def verified(self, result):
        self.set_scanning(False); self.completed=result
        if result.get('driver',{}).get('acquired') and not result.get('driver',{}).get('canceled') and not result.get('driver',{}).get('partial'):
            selected=self.hub.scan_request['device'];self.hub.verified_backends.add(selected);self.hub.remember('scanner_id',selected)
            self.hub.populate(self.hub.scanner,self.hub.scanners,selected,'No scanner');self.hub.fallback_running=False
        self.open_button.setEnabled(True)
        self.message.setText(f'Original retained: {result["width"]} × {result["height"]} pixels, {result["format"]}. '
            'Open in Cropper when ready. A late cancel retains the finished scan too.\n'+result['original'])
        if result.get('pages'):self.message.setText(str(len(result['pages']))+' feeder pages verified. '+result.get('driver',{}).get('warning','')+' Review all pages in Quick Copy / Cropper. '+('Page limit reached; additional originals may remain in the feeder.' if result.get('driver',{}).get('limit_reached') else ''))
        from app.services.imaging import load_image
        from app.ui.canvas import pixmap
        # Decode only a bounded preview. Full original pixels remain on disk.
        path=result['original']
        callback=None if self.acquisition_preview else self.completion_callback
        if not self.acquisition_preview:self.completion_callback=None;self.completion_owner=None;self.folder_root=None
        if callback:callback(result)
        elif self.acquisition_preview or self.preview_image is None or self.preview_context!=self.area_context:
            acquired_region=list(self.hub.scan_request.get('region',[0,0,1,1]));context=self.area_context
            self.hub.w.run(lambda:load_image(path,1500),lambda image:self.display_preview(image,acquired_region,context))
        else:self.message.setText(self.message.text()+'\nFull-bed preview retained. Drag another area or scan this area again.')
    def scan_now(self,checked=False,preview=False):
        import time
        if preview:self.preview_pending=True
        if self.hub.scan_process.active:
            if self.hub.scan_action in ('devices','capabilities'):self.user_canceled=False;self.pending_scan=True;self.message.setText('Connecting, then scanning once…')
            else:self.message.setText('A scanner operation is already active.')
            return
        if self.verifier.active:self.message.setText('Verifying the completed transfer.');return
        self.pending_scan=True
        self.cancel_button.setEnabled(True)
        self.hub.fallback_attempts=0;self.hub.fallback_tried=set();self.hub.fallback_errors=[];self.hub.fallback_running=False;self.user_canceled=False
        if self.sources and time.monotonic()-self.capability_time<300:self.pending_scan=False;self.scan()
        elif self.device.currentData():self.connect_device()
        else:self.hub.refresh()

    def error(self, message):
        self.pending_scan=False
        self.preview_pending=False
        self.retry_request=None
        if self.completion_owner and hasattr(self.completion_owner,'scan_failed'):self.completion_owner.scan_failed(message)
        self.completion_callback=None;self.completion_owner=None;self.folder_root=None;self.request_overrides=None
        self.set_scanning(False)
        suffix=('\nAcquisition folder retained: '+str(self.folder)) if self.folder else ''
        self.hub.fallback_running=False
        self.message.setText('Error: '+message+suffix+'\nNo further automatic scan will run. Check the connection or driver, then retry explicitly.')
    def display_preview(self,image,acquired_region=None,context=None):
        from app.services.cropping import CropRegion
        if context is not None and context!=self.area_context:return
        self.preview_image=image
        self.preview_context=self.area_context
        self.preview_acquired_region=list(acquired_region or self.hub.scan_request.get('region',[0,0,1,1]))
        self.preview_canvas.display(image,[CropRegion([(0,0),(image.width,0),(image.width,image.height),(0,image.height)])])
        self.draw_area();self.message.setText('Preview ready. Drag a rectangle over the area you want, then click Scan Now. Save the area by name to reuse it.')
    def link_fallback(self):
        from PySide6.QtWidgets import QInputDialog
        selected=self.device.currentData()
        if selected not in self.hub.verified_backends:self.message.setText('A successful real scan through this backend is required before it can be an automatic fallback.');return
        options=[d for d in self.hub.scanners if d['id']!=selected]
        if not options:return
        label,ok=QInputDialog.getItem(self,'Link fallback to the same physical scanner','Choose the primary interface of this SAME scanner. Do not link a different physical device.',[d['name'] for d in options],0,False)
        if ok:
            primary=next(d['id'] for d in options if d['name']==label);links=self.hub.w.db.get('scanner_fallbacks',{});links[primary]=selected;self.hub.remember('scanner_fallbacks',links);self.message.setText('Fallback linked. Automatic retry is permitted only before acquisition, once, while this backend remains verified in this session.')
    def clear_preview(self):
        self.preview_image=None;self.preview_acquired_region=None;self.preview_context=None
        if hasattr(self,'preview_canvas'):
            self.preview_canvas.scene().clear();self.preview_canvas.outlines=[];self.preview_canvas.has_image=False
            self.preview_canvas.anchor=None;self.preview_canvas.drawing=None
            self.preview_canvas.setSceneRect(0,0,560,240)
            text=self.preview_canvas.scene().addText('1. Click Preview to see the scanner bed.\n\n2. Hold the left mouse button and drag an area.\n\n3. Click Scan Now to scan only that area.');text.setDefaultTextColor(QColor('#7e99be'));text.setPos(20,55)
            self.preview_canvas.fitInView(self.preview_canvas.sceneRect(),Qt.KeepAspectRatio)

    def coordinates_changed(self,*_):
        values=[box.value() for box in self.region]
        if hasattr(self,'area_summary'):self.area_summary.setText(f'{values[2]:g} × {values[3]:g} mm · left {values[0]:g}, top {values[1]:g}')
        if hasattr(self,'paper') and self.sources and 0<=self.source.currentIndex()<len(self.sources):
            caps=self.sources[self.source.currentIndex()];a4=[0,0,min(210,caps['width_mm']),min(297,caps['height_mm'])] if caps['width_mm']>=209.9 and caps['height_mm']>=296.9 else [0,0,210,297];choices=[[0,0,caps['width_mm'],caps['height_mm']],a4,[0,0,215.9,279.4]]
            self.paper.setCurrentIndex(next((i for i,r in enumerate(choices) if all(abs(a-b)<.01 for a,b in zip(values,r))),3))
        if hasattr(self,'basic_area'):self.basic_area.setText(f'{self.paper.currentText()} · {values[2]:g} × {values[3]:g} mm')

    def set_region(self,region,redraw=True):
        for box,value in zip(self.region,region):box.blockSignals(True);box.setValue(value);box.blockSignals(False)
        self.coordinates_changed()
        if redraw and self.preview_image and self.preview_context==self.area_context:
            from app.services.cropping import CropRegion
            x,y,w,h=self.preview_acquired_region;left,top,width,height=region;W,H=self.preview_image.size
            if left>=x-.01 and top>=y-.01 and left+width<=x+w+.01 and top+height<=y+h+.01:
                a,b=(left-x)/w*W,(top-y)/h*H;c,d=(left+width-x)/w*W,(top+height-y)/h*H
                self.preview_canvas.display(self.preview_image,[CropRegion([(a,b),(c,b),(c,d),(a,d)])]);self.preview_canvas.draw_mode=False
            else:
                self.preview_canvas.display(self.preview_image,[]);self.draw_area();self.message.setText('Area selected. Click Preview to see the full bed; the current image covers a smaller region.')

    def paper_changed(self,index):
        if not self.sources:self.message.setText('Connect to a scanner first.');return
        if index==0:self.full_bed();return
        if index==3:self.draw_area();return
        region=[0,0,210.,297.] if index==1 else [0,0,215.9,279.4]
        try:
            caps=self.sources[self.source.currentIndex()];check_scan_request(caps,self.dpi.currentData(),self.color.currentData(),region)
            # Some drivers report A4 a fraction of a millimetre short. Use their
            # actual usable bed explicitly rather than requesting an impossible extent.
            limited=region[2]>caps['width_mm']+.00001 or region[3]>caps['height_mm']+.00001
            region[2]=min(region[2],caps['width_mm']);region[3]=min(region[3],caps['height_mm'])
            self.set_region(region);self.paper.setCurrentIndex(index)
            note=f' Driver usable area: {region[2]:g} × {region[3]:g} mm.' if limited else ''
            self.message.setText(('A4' if index==1 else 'Letter')+' selected.'+note+' Scan Now uses this area; Preview shows the full bed.')
        except ValueError as error:self.coordinates_changed();self.message.setText('Paper does not fit this scanner/source: '+str(error)+'. Choose another source or draw a smaller area.')

    def refresh_area_presets(self,selected=None):
        self.area_presets.clear();self.area_presets.addItem('Choose a saved area',None)
        for name,preset in self.hub.w.db.get('scan_area_presets',{}).items():
            if (preset['device'],preset['source'])==self.area_context:self.area_presets.addItem(name,name)
        if selected is not None:self.area_presets.setCurrentIndex(max(0,self.area_presets.findData(selected)))

    def save_area(self):
        if not self.sources:self.message.setText('Connect to a scanner before saving an area.');return
        region=[box.value() for box in self.region]
        try:check_scan_request(self.sources[self.source.currentIndex()],self.dpi.currentData(),self.color.currentData(),region)
        except ValueError as error:self.message.setText(str(error));return
        name,ok=QInputDialog.getText(self,'Save scan area','Name this area (for example, Passport sheet):')
        if not ok:return
        name=name.strip();presets=copy.deepcopy(self.hub.w.db.get('scan_area_presets',{}))
        if name in presets and QMessageBox.question(self,'Replace saved area?',f'Replace the saved area “{name}”?',QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        presets[name]=dict(device=self.area_context[0],source=self.area_context[1],region=region)
        try:self.hub.remember('scan_area_presets',presets)
        except ValueError as error:self.message.setText(str(error));return
        self.refresh_area_presets(name);self.message.setText(f'Saved “{name}”. Choose it from Saved areas to reuse it on this scanner/source.')

    def use_preset(self,index):
        name=self.area_presets.itemData(index)
        if name is None:return
        preset=self.hub.w.db.get('scan_area_presets',{}).get(name)
        try:
            if not preset or (preset['device'],preset['source'])!=self.area_context:raise ValueError('This saved area belongs to another scanner/source')
            check_scan_request(self.sources[self.source.currentIndex()],self.dpi.currentData(),self.color.currentData(),preset['region'])
            self.set_region(preset['region']);self.message.setText(f'“{name}” ready. Scan Now scans this area at the selected resolution.')
        except (ValueError,IndexError) as error:self.message.setText(str(error));self.area_presets.setCurrentIndex(0)

    def remove_area(self):
        name=self.area_presets.currentData()
        if name is None:return
        if QMessageBox.question(self,'Remove saved area?',f'Remove “{name}” from saved areas? Your scans are kept.',QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        presets=copy.deepcopy(self.hub.w.db.get('scan_area_presets',{}));presets.pop(name,None);self.hub.remember('scan_area_presets',presets);self.refresh_area_presets()

    def full_bed(self):
        if self.sources:
            caps=self.sources[self.source.currentIndex()]
            self.set_region([0,0,caps['width_mm'],caps['height_mm']])
            self.apply_area.setChecked(False)
    def draw_area(self):self.preview_canvas.pan_mode=False;self.preview_canvas.setDragMode(QGraphicsView.DragMode.NoDrag);self.preview_canvas.setInteractive(True);self.preview_canvas.draw_mode=True;self.preview_canvas.setCursor(Qt.CrossCursor)
    def pan_preview(self):
        self.preview_canvas.pan_mode=not getattr(self.preview_canvas,'pan_mode',False)
        self.preview_canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if self.preview_canvas.pan_mode else QGraphicsView.DragMode.NoDrag);self.preview_canvas.setInteractive(not self.preview_canvas.pan_mode)
    def area_drawn(self,region):
        if self.preview_image:self.preview_canvas.display(self.preview_image,[region]);self.area_changed()
    def area_changed(self,*_):
        if not self.preview_image or not self.preview_canvas.outlines:return
        from app.services.hardware import preview_to_scanner
        try:
            region=preview_to_scanner(self.preview_canvas.outlines[0].region.points,self.preview_image.size,self.preview_acquired_region)
            caps=self.sources[self.source.currentIndex()];check_scan_request(caps,self.dpi.currentData(),self.color.currentData(),region)
            self.apply_area.blockSignals(True);self.apply_area.setChecked(True);self.apply_area.blockSignals(False)
            self.set_region(region,redraw=False)
            self.message.setText(f'Selected {region[2]:.2f} × {region[3]:.2f} mm. Scan Now scans only this area. Save area… keeps it for next time.')
        except ValueError as error:self.message.setText(str(error))
    def detect_area(self):
        if not self.preview_image:return
        from app.services.documents import detect_card
        from app.services.cropping import CropRegion
        image=self.preview_image
        self.hub.w.run(lambda:detect_card(image),lambda points:self.area_drawn(CropRegion(points)) if points else self.message.setText('No reliable boundary. Draw the rectangle manually.'))

    def open_cropper(self):
        if not self.completed or self.hub.w.busy:return
        path=self.completed['original']
        # Deliberate user navigation: the shared Save/Discard/Cancel gate is authoritative.
        if self.hub.w.open_cropper(load_source=False):
            self.hub.w.cropper.import_sources(paths=[record['original'] for record in self.completed.get('pages') or [self.completed]]); self.hide()

    def show_folder(self):
        from app.services.user_folders import folder
        try:root=folder(self.hub.w.db,'scans')
        except ValueError as error:self.message.setText(str(error));return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))

    def reject(self):
        if self.hub.scan_process.active and self.hub.scan_action=='scan':
            self.message.setText('Scan continues in the background. Reopen Scan Photos to review it.'); self.hide()
        else:super().reject()


class PrintDialog(QDialog):
    def __init__(self, hub, job, folder,warnings=(),printer_id=None):
        super().__init__(hub.w); self.hub=hub; self.job=job; self.folder=folder; self.area=None; self.attempted=False
        self.auto_requested=False;self.direct_requested=False;self.requested_printer=printer_id;self.quality_warnings=bool(warnings)
        self.state='Preparing';self.base_job=copy.deepcopy(job)
        self.pdf_path=folder/'sheet.pdf'
        self.setWindowTitle('Printora — Review PDF and print'); self.resize(930,800)
        screen=QApplication.primaryScreen()
        if screen:self.resize(min(930,screen.availableGeometry().width()-30),min(800,screen.availableGeometry().height()-50))
        root_layout=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);contents=QWidget();outer=QVBoxLayout(contents);scroll.setWidget(contents);root_layout.addWidget(scroll)
        outer.addWidget(text_label('Actual Size / 100% — paper dimensions and orientation follow this reviewed PDF. '
            'No fit, shrink, enlargement or extra copies are applied by Printora. Review driver properties for borderless enlargement.'))
        if warnings:outer.addWidget(text_label('Quality warning: '+'\n'.join(warnings[:5])+'\nIncreasing DPI cannot restore source detail.'))
        form=QFormLayout();outer.addLayout(form);self.printer=QComboBox();form.addRow('Printer',self.printer)
        from app.services.layout import page_size
        width,height=page_size(job.print_settings)
        self.setup_loading=True;self.rebuilding=False
        self.paper=QComboBox();self.paper.addItem('A4 (210 × 297 mm)',[210.,297.])
        if job.print_settings.get('policy')=='document':
            from app.services.documents import PAPERS
            for title,size in PAPERS.items():
                if title!='A4':self.paper.addItem(title,list(size))
            size=job.print_settings.get('document_paper_mm',[210.,297.]);idx=self.paper.findData(size)
            if idx<0:self.paper.addItem(f'Custom {size[0]:g} × {size[1]:g} mm',size);idx=self.paper.count()-1
            self.paper.setCurrentIndex(idx)
        self.orientation=QComboBox();self.orientation.addItems(['Portrait','Landscape']);self.orientation.setCurrentIndex(1 if job.print_settings.get('landscape') else 0)
        self.sets=QSpinBox();self.sets.setRange(1,100);self.sets.setValue(1)
        paper_row=QWidget();paper_layout=QHBoxLayout(paper_row);paper_layout.setContentsMargins(0,0,0,0);paper_layout.addWidget(self.paper,1);paper_layout.addWidget(self.orientation);form.addRow('Paper / orientation',paper_row)
        self.copy_summary=text_label(f'{sum(p.quantity for p in job.photos)} placed copies on {job.page_count} page(s).');form.addRow(self.copy_summary)
        form.addRow('Scaling',text_label('Actual Size / 100% — fixed for exact photo dimensions'))
        self.color=QComboBox();self.color.addItem('Color','color');self.color.addItem('Grayscale','gray');self.color.setCurrentIndex(max(0,self.color.findData(hub.w.db.get('preferred_print_color','color'))))
        copies_row=QWidget();copies_layout=QHBoxLayout(copies_row);copies_layout.setContentsMargins(0,0,0,0);copies_layout.addWidget(self.sets);copies_layout.addWidget(QLabel('sheet set(s)'));copies_layout.addStretch();copies_layout.addWidget(self.color);form.insertRow(2,'Copies / driver color',copies_row)
        self.quick=QCheckBox('Quick Print — Use Saved Printer Settings');self.quick.setChecked(hub.w.db.get('quick_print',False));self.quick.setToolTip('Future Print clicks skip review for this confirmed printer/paper only when readiness and every safety check pass.');form.addRow(self.quick)
        self.document=QPdfDocument(self); self.document.load(str(self.pdf_path))
        self.view=QPdfView(); self.view.setDocument(self.document); self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView);self.view.setMinimumHeight(220); outer.addWidget(self.view,1)
        self.message=text_label('Select a printer to check its paper and printable area.'); outer.addWidget(self.message)
        self.ack=QPushButton('I checked the printer queue and any partial output');self.ack.clicked.connect(self.acknowledge_unknown);outer.addWidget(self.ack);self.ack.hide()
        row=QHBoxLayout(); outer.addLayout(row)
        zoom=QComboBox();zoom.addItems(['Fit page','Fit width','100%','150%']);zoom.activated.connect(lambda i:self.view.setZoomMode(QPdfView.ZoomMode.FitInView if i==0 else QPdfView.ZoomMode.FitToWidth if i==1 else QPdfView.ZoomMode.Custom) or (self.view.setZoomFactor(1 if i==2 else 1.5) if i>=2 else None));row.addWidget(zoom)
        self.properties=QPushButton('Printer properties'); self.properties.clicked.connect(self.show_properties); row.addWidget(self.properties)
        self.check=QPushButton('Recheck printer'); self.check.clicked.connect(self.probe); row.addWidget(self.check)
        self.submit=QPushButton('Print');self.submit.setObjectName('primary');self.submit.setToolTip('Submit this reviewed PDF once. Physical completion must be checked at the printer.'); self.submit.setEnabled(False); self.submit.clicked.connect(self.print_now); row.addWidget(self.submit)
        self.process=HardwareProcess(self); self.action=None
        self.process.succeeded.connect(self.result); self.process.failed.connect(self.error)
        self.printer.activated.connect(self.choose_printer)
        self.paper.activated.connect(self.rebuild);self.orientation.activated.connect(self.rebuild);self.sets.valueChanged.connect(self.rebuild)
        self.setup_loading=False;self.update_devices()
        self.color.activated.connect(lambda _:setattr(self,'auto_requested',False))

    def rebuild(self,*_):
        if self.setup_loading or self.rebuilding or self.attempted or self.process.active:return
        self.auto_requested=False;self.area=None;self.submit.setEnabled(False);self.rebuilding=True
        job=copy.deepcopy(self.base_job);settings=job.print_settings
        changed=bool(settings.get('landscape'))!=(self.orientation.currentIndex()==1) or settings.get('policy')=='document' and settings.get('document_paper_mm')!=self.paper.currentData()
        try:
            if changed:
                from app.services.layout import page_size
                old_w,old_h=page_size(settings);settings['landscape']=self.orientation.currentIndex()==1
                if settings.get('policy')=='document':
                    settings['document_paper_mm']=self.paper.currentData();new_w,new_h=page_size(settings)
                    for r in job.placements:r.x+=(new_w-old_w)/2;r.y+=(new_h-old_h)/2
                else:
                    job.placements=auto_layout(job.photos,settings);job.page_count=max(r.page for r in job.placements)+1
            from app.services.print_transactions import repeat_sheets
            job=repeat_sheets(job,self.sets.value());validate_layout(job)
        except ValueError as error:self.rebuilding=False;self.message.setText('Review layout: '+str(error));return
        self.message.setText('Preparing updated PDF. Explicit paper changes re-arrange photo sheets at their exact size.')
        # QPdfView can retain an asynchronous Windows file handle after close().
        # Each reviewed revision therefore gets a new owned file, never an overwrite.
        revision=self.folder/('sheet-'+uuid.uuid4().hex+'.pdf')
        def done(_):
            self.job=job;self.pdf_path=revision;self.rebuilding=False;self.document.close();self.document.load(str(revision));self.copy_summary.setText(f'{sum(p.quantity for p in job.photos)} placed copies on {job.page_count} page(s).');self.probe()
        def failed(error):self.rebuilding=False;self.error(str(error))
        from app.services.pdf import export_pdf
        self.hub.w.run(lambda:export_pdf(job,revision,dpi=int(settings.get('dpi',300))),done,failed)

    def update_devices(self):
        if self.process.active:return
        if self.requested_printer and not any(p['id']==self.requested_printer for p in self.hub.printers):
            self.printer.clear();self.printer.addItem('Selected printer unavailable',None)
            for printer in self.hub.printers:self.printer.addItem(printer['name'],printer['id'])
            self.message.setText('The selected printer is unavailable. Refresh devices or explicitly choose another printer.');self.show();return
        self.hub.populate(self.printer,self.hub.printers,self.requested_printer or self.hub.printer.currentData(),'Not Found — Refresh Devices on dashboard')
        self.probe()
    def choose_printer(self,*_):
        self.requested_printer=self.printer.currentData();self.auto_requested=False;self.direct_requested=False;self.probe()

    def probe(self,*_):
        if self.process.active or self.attempted:return
        self.submit.setEnabled(False); self.area=None
        if not self.printer.currentData():self.message.setText('Printer Not Found. Install a Windows driver, then refresh devices.');return
        self.printer.setEnabled(False)
        for control in (self.paper,self.orientation,self.sets):control.setEnabled(False)
        self.action='printer_caps'; self.message.setText('Checking installed driver paper and printable limits…')
        request=dict(action=self.action,printer=self.printer.currentData(),landscape=bool(self.job.print_settings.get('landscape')))
        if self.job.print_settings.get('policy')=='document':request['paper_mm']=self.job.print_settings['document_paper_mm']
        self.process.start('printer',request,25000)

    def result(self,result):
        if self.action=='printer_caps':
            self.printer.setEnabled(True)
            for control in (self.paper,self.orientation,self.sets):control.setEnabled(True)
            try:
                self.area=PrintableArea(**result['area']); preflight_print(self.job,self.area)
                from app.services.print_transactions import unresolved
                pending=unresolved(data_root())
                if pending:
                    self.auto_requested=False;self.ack.show();self.show();self.message.setText('OutcomeUnknown: a previous driver submission has no confirmed result. Check the queue and any partial output before acknowledging. No automatic retry.');self.submit.setEnabled(False);return
                self.ack.hide()
                status=next((p['status'] for p in self.hub.printers if p['id']==self.printer.currentData()),'Physical readiness unverified')
                self.message.setText(f'{self.job.page_count} page(s), {sum(p.quantity for p in self.job.photos)} placed copies. '
                    f'Driver preflight passed. {status}. Check paper, ink and the printer queue before confirming.')
                self.submit.setEnabled(status not in ('Offline','Error'))
                if self.auto_requested:
                    self.auto_requested=False
                    direct=self.direct_requested;self.direct_requested=False
                    if (status=='Ready' or direct and status not in ('Offline','Error','Physical readiness unverified')) and not self.quality_warnings:self.print_now(automatic=not direct)
                    else:self.show();self.message.setText('Automatic submission stopped: printer readiness is unknown, unavailable or quality needs review. Confirm manually after checking the printer. No print was submitted.')
            except ValueError as error:self.error(str(error))
        elif self.action=='print':
            if self.hub.print_dialog is self:self.hub.printing=False
            self.state='SubmittedToDriver';self.hub.w.notify('SubmittedToDriver — physical output unconfirmed.')
            self.message.setText(result['status']+'. Confirm output at the printer. Orders were not marked Completed.\nPDF retained: '+str(self.pdf_path))
        elif self.action=='properties':
            self.printer.setEnabled(True)
            self.message.setText('Printer properties opened. Close them, then Recheck printer before submitting.'); self.submit.setEnabled(False)

    def show_properties(self):
        if self.process.active or not self.printer.currentData() or self.attempted:return
        self.submit.setEnabled(False);self.area=None;self.auto_requested=False; self.action='properties'
        self.process.start('printer',dict(action='properties',printer=self.printer.currentData()),15000)

    def print_now(self,checked=False,automatic=False):
        if self.process.active or self.attempted or self.rebuilding or self.area is None:return
        try:
            from app.services.record_recovery import checked_document
            from app.services.print_transactions import unresolved
            checked_document(self.job);preflight_print(self.job,self.area)
            if unresolved(data_root()):raise ValueError('OutcomeUnknown: check and acknowledge the earlier submission before printing')
        except ValueError as error:self.error(str(error));return
        name=self.printer.currentData()
        status=next((p['status'] for p in self.hub.printers if p['id']==name),None)
        if status is None or status in ('Offline','Error') or automatic and (status!='Ready' or self.quality_warnings):self.error('Printer readiness or quality requires review. No submission was made.');return
        self.hub.remember('preferred_printer',name)
        from app.services.print_transactions import profile_key
        profiles=self.hub.w.db.get('confirmed_print_profiles',{});profiles.setdefault(name,[])
        key=profile_key(self.job,self.color.currentData())
        if key not in profiles[name]:profiles[name].append(key)
        self.hub.remember('confirmed_print_profiles',profiles);self.hub.remember('quick_print',self.quick.isChecked())
        self.hub.remember('preferred_print_color',self.color.currentData())
        self.attempted=True; self.hub.printing=True; self.action='print'
        self.state='Preparing';self.color.setEnabled(False);self.quick.setEnabled(False)
        for control in (self.paper,self.orientation,self.sets):control.setEnabled(False)
        self.submit.setEnabled(False); self.printer.setEnabled(False); self.check.setEnabled(False); self.properties.setEnabled(False)
        self.message.setText('Submitting… Do not retry until you have checked the printer queue.')
        self.process.start('printer',dict(action='print',printer=name,folder=str(self.folder),job=self.job.to_dict(),color=self.color.currentData(),pdf_name=self.pdf_path.name,automatic=bool(automatic)),180000)

    def acknowledge_unknown(self):
        from app.services.print_transactions import unresolved,acknowledge
        try:acknowledge(unresolved(data_root()));self.ack.hide();self.probe()
        except OSError as error:self.error('Could not record queue review: '+str(error))

    def error(self,error):
        if self.action=='print' and self.hub.print_dialog is self:self.hub.printing=False
        if not self.attempted:
            self.printer.setEnabled(True)
            for control in (self.paper,self.orientation,self.sets):control.setEnabled(True)
        self.show()
        self.submit.setEnabled(False)
        self.state='OutcomeUnknown' if self.attempted and (self.folder/'status.json').exists() else 'SubmissionFailed'
        self.hub.w.notify(self.state+' — '+str(error))
        self.message.setText('Error: '+error+'\nPDF retained at '+str(self.pdf_path)+
                             ('\nThis request cannot be resubmitted. Check the queue before creating a new request.' if self.attempted else ''))

    def reject(self):
        if self.process.active and self.action=='print':
            self.message.setText('Wait for submission to finish. If the driver times out, check the queue before retrying.');return
        super().reject()
