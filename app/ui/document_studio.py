"""Quick Copy and existing-card reproduction; no identity-content editing tools."""
from app.services.user_folders import dialog_folder,dialog_output
import copy,json
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QComboBox,
    QSpinBox,QDoubleSpinBox,QCheckBox,QListWidget,QScrollArea,QSplitter,QFileDialog,QMessageBox,QInputDialog,QSizePolicy)
from app.core.database import data_root
from app.services.documents import DocumentSession,DocumentPage,PAPERS,detect_card,propose_card
from app.services.cropping import CropRegion
from app.services.imaging import load_image
from app.services.pdf import export_pdf
from app.services.export_safety import check_export_target
from app.ui.cropper import CropCanvas
from app.ui.panels import AdaptivePanel
from app.services.user_folders import folder,output_path

class DocumentStudio(QWidget):
    def __init__(self,w,kind):
        super().__init__();self.w=w;self.kind=kind;self.session=DocumentSession(data_root(),kind);self.dirty=False;self.loading=False;self.reviewed=set();self.current_size=None;self.scan_generation=0
        self.action_buttons={};self.simple_inflight=False;self.set_active=False;self.copy_batch=[];self.simple_pending=None;self.simple_mode=None;self.pending_nid_preview=False;self.preview_dialog=None
        self.pending_delivery=None;self.delivery_timer=QTimer(self);self.delivery_timer.setSingleShot(True);self.delivery_timer.timeout.connect(self.deliver_scan)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(4);header=QHBoxLayout();outer.addLayout(header)
        title=QLabel('ID Card Print' if kind=='nid' else 'Quick Copy');title.setObjectName('section');header.addWidget(title)
        desc=QLabel('Scan or import Front and Back → Preview PDF → adjust the corners → Print.' if kind=='nid' else 'Color or black & white. Use Print Set for multiple pages.');desc.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);desc.setToolTip(desc.text());header.addWidget(desc,1)
        actions=QHBoxLayout();outer.addLayout(actions)
        for text,fn in ([('Scan Front',lambda:self.scan('Front')),('Scan Back',lambda:self.scan('Back'))] if kind=='nid' else [('Copy / Scan page',lambda:self.scan('Page'))]):self.button(actions,text,fn)
        self.button(actions,'Import files',self.import_files);self.button(actions,'Save session',self.save_session);self.button(actions,'Open session',self.open_session);self.button(actions,'Clear session',self.clear)
        self.auto_pending=None
        split=QSplitter();split.setChildrenCollapsible(False);split.setHandleWidth(7);self.workspace_splitter=split;outer.addWidget(split,1)
        settings=QWidget();form=QFormLayout(settings);form.setRowWrapPolicy(QFormLayout.WrapAllRows);self.fields={}
        self.printer=QComboBox();form.addRow('Printer',self.printer)
        self.scanner=QComboBox();form.addRow('Scanner',self.scanner)
        self.button(form,'Refresh scanners / printers',self.w.hardware.refresh)
        self.scanner.activated.connect(self.scanner_changed)
        self.button(form,'Scanner DPI / source settings',self.scanner_settings)
        self.paper=QComboBox();self.paper.addItems(list(PAPERS));form.addRow('Paper',self.paper)
        self.paper.addItem('Custom');self.add(form,'paper_width','Custom paper width (mm)',50,1000,210);self.add(form,'paper_height','Custom paper height (mm)',50,1000,297)
        preferred=w.db.get('document_paper','A4');self.paper.setCurrentText(preferred if self.paper.findText(preferred)>=0 else 'Custom')
        for key,value in zip(('paper_width','paper_height'),w.db.get('document_paper_mm',[210,297])):self.fields[key].setValue(value)
        self.page_dpi=QDoubleSpinBox();self.page_dpi.setRange(50,9600);self.page_dpi.setValue(300);form.addRow('Imported page DPI (verify)',self.page_dpi);self.page_dpi.valueChanged.connect(self.page_dpi_changed)
        self.add(form,'scan_dpi','Scan resolution (DPI)',50,9600,150 if kind=='copy' else 300,integer=True)
        self.landscape=QCheckBox('Landscape');self.landscape.setChecked(w.db.get('document_landscape',False));form.addRow(self.landscape)
        self.center=QCheckBox('Center on page');self.center.setChecked(True);self.center.toggled.connect(self.changed);form.addRow(self.center)
        self.add(form,'copies','Copy quantity' if kind=='copy' else 'Copies / pairs',1,100,1,integer=True)
        self.add(form,'margin','Margins (mm)',0,100,10)
        self.color=QComboBox();self.color.addItems(['color','gray','mono']);form.addRow('Color mode',self.color)
        self.color.setCurrentText(w.db.get('document_color','color'))
        self.quality=QComboBox();self.quality.addItems(['Mixed document','Text document','Photograph']);form.addRow('Quality preset',self.quality)
        self.scale_mode=QComboBox();self.scale_mode.addItem('Actual size — scan DPI','actual');self.scale_mode.addItem('Fit to paper','fit');self.scale_mode.addItem('Custom scale','custom');form.addRow('Sizing policy',self.scale_mode)
        if kind=='copy':self.scale_mode.setCurrentIndex(self.scale_mode.findData('fit'))
        self.add(form,'scale','Custom scale (%)',5,400,100)
        for name in ('brightness','contrast','sharpness'):self.add(form,name,name.title(),0,3,1)
        if kind=='nid':
            self.add(form,'card_width','Card bounds width (mm)',10,250,85.6);self.add(form,'card_height','Card bounds height (mm)',10,250,53.98)
            self.add(form,'spacing','Spacing (mm)',0,100,10);self.add(form,'top','Top position (mm)',0,250,20)
            self.add(form,'pairs_per_sheet','Pairs per sheet',1,10,1,integer=True)
            self.actual_card=QCheckBox('Actual size from scan DPI');form.addRow(self.actual_card)
            self.align=QComboBox();self.align.addItems(['center','left','right']);form.addRow('Alignment',self.align)
            self.center.setText('Center both sides on page')
            self.center.setToolTip('Center the complete front/back group horizontally and vertically, keeping both sides and their spacing together.')
            self.center.toggled.connect(self.centering_changed);self.centering_changed()
            note=QLabel('Card proportions stay locked; bounds never stretch the image.');note.setWordWrap(True);form.addRow(note)
            self.button(form,'Optional ID-1 / CR80 bounds',lambda:self.card_preset())
            self.button(form,'Swap Front / Back',self.swap)
        else:
            self.auto_print=QCheckBox('Auto Print After Scan');self.auto_print.setToolTip('Off by default. Requires explicit confirmation and confirmed printer readiness.');self.auto_print.toggled.connect(self.confirm_auto);form.addRow(self.auto_print)
            self.auto_confirmed=None
        self.button(form,'Confirm current crop',self.confirm_crop)
        self.button(form,'Draw crop',lambda:self.draw_crop())
        self.button(form,'Auto Detect boundary',self.detect)
        self.button(form,'Reset / Full image',self.reset_crop)
        self.button(form,'Rotate clockwise',self.rotate)
        self.button(form,'Replace current side / page',lambda:self.import_files(replace=True))
        from app.ui.workflow_settings import WorkflowSettings,move_rows
        self.advanced_settings=WorkflowSettings(self,'Quick Copy' if kind=='copy' else 'ID Card Print')
        self.advanced_settings.closed.connect(self.refresh_nid_preview)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(settings);self.advanced_settings.add_widget(scroll)
        basic=QWidget();basic_form=QFormLayout(basic);basic_form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        if kind=='copy':move_rows(form,basic_form,[self.scanner,self.printer,self.fields['copies']])
        self.settings_summary=QLabel();self.settings_summary.setWordWrap(True)
        if kind=='copy':basic_form.addRow(self.settings_summary)
        self.controls_panel=AdaptivePanel(basic,w.db,kind+'_controls','Copy controls',default_width=290,minimum_width=240);split.addWidget(self.controls_panel)
        if kind=='nid':self.controls_panel.hide()
        center=QWidget();cl=QVBoxLayout(center);bar=QHBoxLayout();cl.addLayout(bar)
        self.canvas=CropCanvas();self.canvas.setMinimumSize(160,60)
        for label,fn in [('Fit',lambda:self.canvas.fitInView(self.canvas.sceneRect(),Qt.KeepAspectRatio)),('100%',self.canvas.resetTransform),('＋',lambda:self.canvas.scale(1.2,1.2)),('−',lambda:self.canvas.scale(1/1.2,1/1.2)),('Pan',self.toggle_pan)]:self.button(bar,label,fn)
        self.advanced_settings.add_layout(bar)
        from app.ui.preview_workspace import FloatingFit
        self.canvas_fit=FloatingFit(self.canvas);cl.setContentsMargins(0,0,0,0);cl.addWidget(self.canvas,1);self.measure=QLabel('Import or scan a page. Draw a crop on the preview; drag corners/edges to adjust.');self.measure.hide();split.addWidget(center)
        pages=QWidget();pl=QVBoxLayout(pages);self.list=QListWidget();self.list.setMinimumWidth(95);self.list.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored);pl.addWidget(self.list,1)
        for label,fn in [('Move up',lambda:self.move(-1)),('Move down',lambda:self.move(1)),('Remove',self.remove)]:self.button(pl,label,fn)
        self.pages_panel=AdaptivePanel(pages,w.db,kind+'_pages','Pages',default_width=180,minimum_width=140);split.addWidget(self.pages_panel);split.setStretchFactor(1,1);self.controls_panel.attach(split);self.pages_panel.attach(split)
        self.canvas.changed.connect(self.crop_changed);self.canvas.drawn.connect(self.drawn);self.list.currentRowChanged.connect(self.show_page)
        row=QHBoxLayout();outer.addLayout(row);self.primary_print=self.button(row,'Print',self.print_job);self.primary_print.setObjectName('primary');self.button(row,'Save PDF',self.export);self.button(row,'Preview adjustments',self.preview_adjustments);self.button(row,'Export current image',self.export_image)
        self.message=QLabel('Waiting for Front' if kind=='nid' else 'Ready. Add pages in order, then preview or copy.');self.message.setWordWrap(True);outer.addWidget(self.message)
        self.paper.currentIndexChanged.connect(self.changed);self.landscape.toggled.connect(self.changed);self.color.currentIndexChanged.connect(self.changed);self.scale_mode.currentIndexChanged.connect(self.changed)
        self.printer.activated.connect(self.printer_changed)
        self.quality.currentIndexChanged.connect(self.quality_changed)
        if self.kind=='nid':self.actual_card.toggled.connect(self.changed);self.align.currentIndexChanged.connect(self.changed)
        # Keep one set of controls; advanced actions live in this workspace's Settings.
        keep={'Scan Front','Scan Back','Import files'} if kind=='nid' else set()
        for title,button in list(self.action_buttons.items()):
            if button.parentWidget() is self and title not in keep:self.advanced_settings.add_widget(button)
        for i in reversed(range(bar.count())):
            item=bar.takeAt(i)
            if item.widget():self.advanced_settings.add_widget(item.widget())
        for title in ('Move up','Move down','Remove'):
            button=next((b for b in pages.findChildren(QPushButton) if b.text()==title),None)
            if button:self.advanced_settings.add_widget(button)
        if kind=='copy':
            self.color_copy=self.button(actions,'Copy Color',lambda:self.start_copy('color'))
            self.bw_copy=self.button(actions,'Copy Black && White',lambda:self.start_copy('gray'))
            self.print_set_button=self.button(actions,'Print Set',lambda:self.start_copy(self.color.currentText(),True))
        else:self.preview_pdf_button=self.button(actions,'Preview PDF',self.preview_nid)
        self.settings_button=self.button(actions,'Settings',self.advanced_settings.open_settings)
        from app.ui.icons import icon
        self.settings_button.setText('');self.settings_button.setIcon(icon('settings'));self.settings_button.setToolTip('Workspace settings');self.settings_button.setAccessibleName('Workspace settings');self.settings_button.setFixedWidth(34)
        self.save_defaults_button=QPushButton('Save as workspace defaults');self.save_defaults_button.clicked.connect(self.save_defaults);self.advanced_settings.add_widget(self.save_defaults_button)
        self.set_actions=QWidget();set_row=QHBoxLayout(self.set_actions);self.set_status=QLabel();set_row.addWidget(self.set_status,1)
        self.add_page_button=QPushButton('Add page');self.add_page_button.clicked.connect(self.add_set_page);set_row.addWidget(self.add_page_button)
        self.finish_set_button=QPushButton('Finish & Print');self.finish_set_button.clicked.connect(self.finish_set);set_row.addWidget(self.finish_set_button);outer.insertWidget(2,self.set_actions);self.set_actions.hide()
        defaults=w.db.get('workflow_defaults',{}).get(kind,{})
        if defaults:self.load_settings(defaults)
        self.update_settings_summary()
        self.dirty=False
    def load_settings(self,settings):
        self.loading=True
        try:
            for key,value in settings.items():
                if key in self.fields:self.fields[key].setValue(value)
            name=settings.get('paper',self.paper.currentText())
            if self.paper.findText(name)<0 and 'paper_mm' in settings:self.paper.addItem(name,settings['paper_mm'])
            self.paper.setCurrentText(name);self.color.setCurrentText(settings.get('color',self.color.currentText()))
            self.landscape.setChecked(settings.get('landscape',self.landscape.isChecked()));self.scale_mode.setCurrentIndex(max(0,self.scale_mode.findData(settings.get('scale_mode',self.scale_mode.currentData()))))
            self.center.setChecked(settings.get('center',self.center.isChecked()));self.quality.blockSignals(True);self.quality.setCurrentIndex(settings.get('quality',self.quality.currentIndex()));self.quality.blockSignals(False)
            if self.kind=='nid':self.actual_card.setChecked(settings.get('actual_card',self.actual_card.isChecked()));self.align.setCurrentText(settings.get('align',self.align.currentText()))
        finally:self.loading=False;self.update_settings_summary()
    def save_defaults(self):
        from app.services.workflow_preferences import validate_settings
        try:
            values=copy.deepcopy(self.w.db.get('workflow_defaults',{}));values[self.kind]=validate_settings(self.settings());self.w.db.set('workflow_defaults',values)
            self.message.setText('Workspace defaults saved. Existing saved sessions are unchanged.');self.advanced_settings.status.setText(self.message.text())
        except (ValueError,TypeError,OSError) as error:self.advanced_settings.status.setText('Could not save defaults: '+str(error))
    def update_copy_actions(self):
        if self.kind!='copy':return
        for button in (self.color_copy,self.bw_copy,self.print_set_button):button.setEnabled(not self.simple_inflight and not self.set_active)
        self.set_actions.setVisible(self.set_active)
        self.add_page_button.setEnabled(not self.simple_inflight);self.finish_set_button.setEnabled(not self.simple_inflight and bool(self.copy_batch))
        self.set_status.setText(f'{len(self.copy_batch)} page(s) in this set. Add the next page or finish.')
    def start_copy(self,color,set_mode=False):
        if self.w.busy or self.simple_inflight or self.set_active:return
        self.color.setCurrentText(color if color in ('color','gray','mono') else 'color');self.simple_mode='set' if set_mode else 'single';self.set_active=set_mode;self.copy_batch=[];self.simple_pending=None
        self.add_set_page()
    def add_set_page(self):
        if self.w.busy or self.simple_inflight:return
        self.simple_inflight=True;self.update_copy_actions();self.scan('Page')
    def scan_failed(self,message):
        self.simple_inflight=False;self.simple_pending=None
        if not self.copy_batch:self.set_active=False
        self.update_copy_actions();self.message.setText('Scan stopped: '+str(message)+'. Completed originals are retained; retry explicitly.')
    def deliver_scan(self):
        pending=self.pending_delivery;self.pending_delivery=None
        if pending:
            token,callback,result=pending
            if token==self.scan_generation:callback(result)
    def finish_set(self):
        if self.w.busy or self.simple_inflight or not self.set_active or not self.copy_batch:return
        pages=list(self.copy_batch);self.set_active=False;self.simple_mode=None;self.update_copy_actions();self.print_job(direct=True,pages=pages)
    def preview_nid(self):
        if self.w.busy:return
        if len(self.session.pages)!=2:self.message.setText('Scan or import Front and Back first.');return
        self.reviewed.update(id(p) for p in self.session.pages)
        from app.ui.nid_preview import NIDPreview
        if self.preview_dialog:self.preview_dialog.close()
        self.preview_dialog=NIDPreview(self);self.preview_dialog.show();self.preview_dialog.rebuild()
    def refresh_nid_preview(self):
        if self.kind=='nid' and self.isVisible() and self.w.isVisible() and self.preview_dialog and self.preview_dialog.isVisible() and not self.w.busy:
            if self.preview_dialog.snapshot!=self.preview_dialog.state():self.preview_dialog.rebuild()
    def centering_changed(self,*_):
        manual=not self.center.isChecked()
        self.fields['top'].setEnabled(manual);self.align.setEnabled(manual)
    def quality_changed(self,index):
        self.fields['contrast'].setValue(1.2 if index==1 else 1.)
        self.fields['sharpness'].setValue(1.2 if index in (1,2) else 1.)
        self.changed()
    def button(self,layout,text,fn):
        button=QPushButton(text);button.clicked.connect(fn)
        if isinstance(layout,QFormLayout):layout.addRow(button)
        else:layout.addWidget(button)
        self.action_buttons[text]=button;return button
    def add(self,form,key,label,low,high,value,integer=False):
        box=QSpinBox() if integer else QDoubleSpinBox();box.setRange(low,high);box.setValue(value)
        if not integer:box.setDecimals(2);box.setSingleStep(.1)
        box.valueChanged.connect(self.changed);self.fields[key]=box;form.addRow(label,box)
    def changed(self,*_):
        if not self.loading:self.dirty=True;self.update_settings_summary()
    def update_settings_summary(self):
        if hasattr(self,'settings_summary'):self.settings_summary.setText(f'{self.paper.currentText()} · {int(self.fields["scan_dpi"].value())} DPI · {self.scale_mode.currentText()}')
    def settings(self):
        values={key:box.value() for key,box in self.fields.items()}
        values.update(paper=self.paper.currentText(),landscape=self.landscape.isChecked(),color=self.color.currentText(),scale_mode=self.scale_mode.currentData(),center=self.center.isChecked(),quality=self.quality.currentIndex())
        if self.paper.currentData():values['paper_mm']=self.paper.currentData()
        if self.paper.currentText()=='Custom':values['paper_mm']=[values['paper_width'],values['paper_height']]
        if self.kind=='nid':values.update(actual_card=self.actual_card.isChecked(),align=self.align.currentText())
        return values
    def current(self):
        i=self.list.currentRow();return self.session.pages[i] if 0<=i<len(self.session.pages) else None
    def page_dpi_changed(self,value):
        if self.current() and not self.loading:self.current().dpi=value;self.current().dpi_trusted=True;self.dirty=True
    def draw_crop(self):self.canvas.pan_mode=False;self.canvas.setInteractive(True);self.canvas.draw_mode=True
    def scanner_changed(self,*_):
        index=self.w.hardware.scanner.findData(self.scanner.currentData())
        if index>=0:self.w.hardware.scanner.setCurrentIndex(index);self.w.hardware.select_scanner()
    def scanner_settings(self):
        self.w.hardware.scan_dialog.advanced_settings.open_settings()
    def refresh(self,selected=None):
        old=self.list.currentRow() if selected is None else selected;self.list.blockSignals(True);self.list.clear()
        self.list.addItems([f'{i+1}. {p.label}'+(' ✓' if id(p) in self.reviewed else '') for i,p in enumerate(self.session.pages)]);self.list.setCurrentRow(min(max(0,old),len(self.session.pages)-1));self.list.blockSignals(False);self.show_page()
    def show_page(self,*_):
        page=self.current()
        if not page:self.canvas.scene().clear();self.canvas.outlines=[];self.canvas.has_image=False;self.current_size=None;return
        self.page_dpi.blockSignals(True);self.page_dpi.setValue(page.dpi);self.page_dpi.blockSignals(False)
        def load():
            with Image.open(page.source) as image:
                size=image.size
                if image.getexif().get(274) in (5,6,7,8):size=size[::-1]
            return load_image(page.source,1500),size
        token=page
        def ready(result):
            if self.current() is not token:return
            image,self.current_size=result;self.preview_size=image.size
            sx,sy=self.current_size[0]/image.width,self.current_size[1]/image.height
            points=page.points or [(0,0),(self.current_size[0]-1,0),(self.current_size[0]-1,self.current_size[1]-1),(0,self.current_size[1]-1)]
            regions=[CropRegion([(x/sx,y/sy) for x,y in points])]
            self.canvas.resetTransform();self.canvas.display(image,regions);self.canvas.rotate(page.rotation);self.measure.setText(f'{page.label}: {self.current_size[0]} × {self.current_size[1]} pixels · {page.dpi:g} scan DPI. Original unchanged.')
            if self.auto_pending:
                pages=self.auto_pending;self.auto_pending=None
                if self.w.stack.currentWidget() is self and self.auto_confirmed==self.settings():self.print_job(auto=True,pages=pages)
            if self.simple_pending:
                pages=self.simple_pending;self.simple_pending=None;self.simple_mode=None;self.print_job(direct=True,pages=pages)
            elif self.pending_nid_preview:
                self.pending_nid_preview=False
                if self.w.stack.currentWidget() is self:self.preview_nid()
        self.w.run(load,ready)
    def drawn(self,region):
        self.canvas.outlines.clear();self.store_points(region.points)
        self.show_page()
    def crop_changed(self,*_):
        if self.canvas.outlines:self.store_points(self.canvas.outlines[0].region.points)
    def store_points(self,points):
        page=self.current()
        if not page or not self.current_size:return
        sx,sy=self.current_size[0]/self.preview_size[0],self.current_size[1]/self.preview_size[1]
        page.points=[(x*sx,y*sy) for x,y in points];self.reviewed.discard(id(page));self.dirty=True
        self.measure.setText(f'Selection updated on {page.label}. Confirm crop after checking all four corners.')
    def confirm_crop(self):
        page=self.current()
        if page:self.reviewed.add(id(page));self.dirty=True;self.message.setText(page.label+' reviewed.');self.refresh()
    def reset_crop(self):
        if self.current():self.current().points=[];self.reviewed.discard(id(self.current()));self.dirty=True;self.show_page()
    def detect(self):
        page=self.current()
        if not page:return
        def operation():
            image=load_image(page.source,1500);return image.size,detect_card(image)
        def ready(result):
            if self.current() is not page:return
            size,points=result
            if not points:self.message.setText('No reliable boundary detected. Draw and adjust the four corners manually.');return
            width,height=self.current_size
            page.points=[(x*width/size[0],y*height/size[1]) for x,y in points];self.dirty=True;self.reviewed.discard(id(page));self.show_page()
            self.message.setText('Boundary proposed. Review corners, orientation and Confirm crop; detection can be wrong.')
        self.w.run(operation,ready)
    def rotate(self):
        if self.current():self.current().rotation=(self.current().rotation+90)%360;self.reviewed.discard(id(self.current()));self.dirty=True;self.show_page()
    def toggle_pan(self):
        self.canvas.pan_mode=not getattr(self.canvas,'pan_mode',False)
        self.canvas.setDragMode(CropCanvas.ScrollHandDrag if self.canvas.pan_mode else CropCanvas.NoDrag)
        self.canvas.setInteractive(not self.canvas.pan_mode)
    def move(self,delta):
        i=self.list.currentRow();j=i+delta
        if self.kind=='nid':self.swap();return
        if 0<=i<len(self.session.pages) and 0<=j<len(self.session.pages):self.session.pages[i],self.session.pages[j]=self.session.pages[j],self.session.pages[i];self.dirty=True;self.refresh(j)
    def swap(self):
        if len(self.session.pages)==2:
            self.session.pages.reverse();self.session.pages[0].label='Front';self.session.pages[1].label='Back';self.dirty=True;self.refresh()
    def remove(self):
        if self.current():self.session.pages.pop(self.list.currentRow());self.dirty=True;self.refresh()
    def card_preset(self):self.fields['card_width'].setValue(85.6);self.fields['card_height'].setValue(53.98)
    def import_files(self,checked=False,replace=False,paths=None):
        if self.w.busy:return
        if paths is None:paths,_=QFileDialog.getOpenFileNames(self,'Import existing documents',dialog_folder(self.w.db,'input',self.w.notify),'Images and PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf)')
        if not paths:return
        target=self.current();settings=self.settings();generation=self.scan_generation
        def operation():
            added=[];errors=[]
            for path in paths:
                try:
                    if Path(path).suffix.lower()=='.pdf':added.extend(self.session.import_pdf(path))
                    else:added.append(self.session.import_image(path,label='Front' if self.kind=='nid' and not self.session.pages else 'Back' if self.kind=='nid' else 'Page'))
                except Exception as error:errors.append(Path(path).name+': '+str(error))
            if self.kind=='nid':
                for page in added:
                    try:
                        def area(points):return abs(sum(x*points[(i+1)%4][1]-y*points[(i+1)%4][0] for i,(x,y) in enumerate(points)))/2
                        regions=propose_card(page);page.points=max(regions,key=area) if regions else []
                        paired=len(regions)==2 and min(map(area,regions))>=max(map(area,regions))*.5
                        if len(added)==1 and len(self.session.pages)==1 and paired:
                            page.points=regions[0]
                            back=DocumentPage(page.source,page.dpi,regions[1],label='Back',dpi_trusted=page.dpi_trusted);self.session.pages.append(back);added.append(back);break
                    except (OSError,ValueError) as error:errors.append(page.label+': '+str(error))
            return added,errors
        def ready(result):
            added,errors=result
            if generation!=self.scan_generation:return
            if replace and target and added:
                index=self.session.pages.index(target);self.session.pages.remove(target)
                if self.kind=='nid':
                    self.session.pages.remove(added[0]);added[0].label=target.label;self.session.pages.insert(index,added[0])
            if self.kind=='nid' and len(self.session.pages)>2:self.message.setText('Only two sides can be printed. Remove extra pages or clear and import two sides.');self.refresh();return
            if self.kind=='nid':
                for index,page in enumerate(self.session.pages):page.label='Front' if index==0 else 'Back'
                self.pending_nid_preview=len(self.session.pages)==2 and self.w.stack.currentWidget() is self
            self.dirty=True;self.message.setText(f'{len(added)} imported; {len(errors)} failed.'+('\n'+'\n'.join(errors) if errors else ' Originals retained; review the crop.'));self.refresh()
        self.w.run(operation,ready)
    def import_scans(self,records):
        if self.w.busy:return
        def operation():
            return [self.session.import_image(r['original'],dpi=r.get('driver',{}).get('dpi',300),label='Page') for r in records]
        def ready(pages):self.dirty=True;self.refresh();self.message.setText(f'{len(pages)} verified scans imported with acquisition DPI. Originals retained.')
        self.w.run(operation,ready)
    def scan(self,side):
        if self.w.busy:return
        if self.w.hardware.scan_process.active and self.w.hardware.scan_action not in ('devices','capabilities'):
            self.scan_failed('Another scanner operation is active');return
        scanner=self.w.hardware.scan_dialog;self.scan_generation+=1;token=self.scan_generation
        self.scanner_changed();scanner.request_overrides=dict(dpi=int(self.fields['scan_dpi'].value()),color='gray' if self.color.currentText() in ('gray','mono') else 'color')
        scanner.folder_root=None;self.message.setText('Scanning '+side+'…')
        def received(result):
            if self.scan_generation!=token:return
            if self.w.busy:
                self.pending_delivery=(token,received,result);self.delivery_timer.start(100);return
            driver=result.get('driver',{});records=result.get('pages') or [result]
            # Durable acquisition lives in Documents/Scans; editable sessions own
            # independent copies so clearing a session cannot remove the scan.
            if any(not Path(record['original']).resolve().is_relative_to(self.session.root.resolve()) for record in records):
                session=self.session
                def retain():
                    import hashlib,shutil,uuid
                    retained=[]
                    for record in records:
                        source=Path(record['original']);target=session.root/(uuid.uuid4().hex+source.suffix.lower());shutil.copyfile(source,target)
                        with source.open('rb') as stream:before=hashlib.file_digest(stream,'sha256').hexdigest()
                        with target.open('rb') as stream:after=hashlib.file_digest(stream,'sha256').hexdigest()
                        if before!=after:raise ValueError('Scan changed while being copied; original retained.')
                        retained.append(dict(record,original=str(target)))
                    return dict(result,pages=retained)
                def retained(mapped):
                    if token!=self.scan_generation:return
                    session.input_paths.extend(record['original'] for record in records);received(mapped)
                self.w.run(retain,retained);return
            pages=[DocumentPage(record['original'],driver.get('dpi',300),label=side) for record in records];page=pages[0]
            if self.kind=='nid':
                old=next((p for p in self.session.pages if p.label==side),None)
                if old:self.session.pages.remove(old)
                self.session.pages.append(page);self.session.pages.sort(key=lambda p:0 if p.label=='Front' else 1)
            else:self.session.pages.extend(pages)
            if self.kind=='copy' and self.simple_mode:
                self.simple_inflight=False;self.copy_batch.extend(pages)
                if not self.set_active and not (driver.get('canceled') or driver.get('partial') or driver.get('warning')):self.simple_pending=list(pages)
                self.update_copy_actions()
            self.dirty=True;self.message.setText('Both Sides Ready — review each outline.' if self.kind=='nid' and len(self.session.pages)==2 else side+' Ready — add another page or review.')
            if self.kind=='nid':
                def propose():
                    preview=load_image(page.source,1500)
                    with Image.open(page.source) as original:size=original.size
                    return [(x*size[0]/preview.width,y*size[1]/preview.height) for x,y in detect_card(preview)]
                def proposed(points):
                    if token!=self.scan_generation:return
                    page.points=points;self.refresh(self.session.pages.index(page));self.message.setText('Card outline ready. Scan the other side, then Preview PDF to adjust and print.' if points else 'No boundary detected. Preview PDF uses the full image; adjust its four square corners there.')
                self.w.run(propose,proposed)
            else:
                if driver.get('canceled') or driver.get('partial') or driver.get('warning'):self.message.setText(f'{len(pages)} completed page(s) retained for review. '+driver.get('warning','Scan canceled after completion.'))
                elif self.w.stack.currentWidget() is self and self.auto_print.isChecked() and not self.simple_mode:
                    if self.auto_confirmed==self.settings():self.auto_pending=pages
                    else:self.message.setText('Settings changed. Review them and enable Auto Print again.')
                self.refresh(self.session.pages.index(page))
        scanner.completion_owner=self;scanner.completion_callback=received;scanner.scan_now()
    def update_printers(self):
        self.w.hardware.populate(self.scanner,self.w.hardware.scanners,self.w.db.get('scanner_id',''),'No scanner — Refresh Devices')
        self.w.hardware.populate(self.printer,self.w.hardware.printers,self.w.db.get('preferred_printer',''),'Not found — Refresh Devices')
        selected=self.paper.currentText()
        row=next((p for p in self.w.hardware.printers if p['id']==self.printer.currentData()),None)
        if row and row.get('paper_sizes'):
            self.paper.blockSignals(True);self.paper.clear()
            for item in row['paper_sizes']:self.paper.addItem(item['name'],item['mm'])
            if row.get('custom_paper'):self.paper.addItem('Custom')
            self.paper.setCurrentIndex(max(0,self.paper.findText(selected)));self.paper.blockSignals(False)
    def printer_changed(self,*_):
        if self.printer.currentData():self.w.hardware.remember('preferred_printer',self.printer.currentData());self.update_printers()
    def confirm_auto(self,enabled):
        if enabled:
            if QMessageBox.question(self,'Enable automatic copy', 'Enable automatic submission after each completed scan using these settings? Unknown printer readiness, clipping or changed settings will stop automatic submission.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:self.auto_print.setChecked(False);return
            self.auto_confirmed=self.settings()
        else:self.auto_confirmed=None
    def make_job(self):
        if self.kind=='nid' and (len(self.session.pages)!=2 or any(id(p) not in self.reviewed for p in self.session.pages)):raise ValueError('Review and Confirm crop for Front and Back first')
        return self.session.job(self.settings())
    def remember_settings(self,settings):
        for key,value in dict(document_paper=settings['paper'],document_paper_mm=list(settings.get('paper_mm',PAPERS.get(settings['paper'],PAPERS['A4']))),document_landscape=settings['landscape'],document_color=settings['color']).items():self.w.hardware.remember(key,value)
    def print_job(self,checked=False,auto=False,pages=None,direct=False):
        if self.w.busy:return
        settings=self.settings()
        if self.kind=='nid' and (len(self.session.pages)!=2 or any(id(p) not in self.reviewed for p in self.session.pages)):self.message.setText('Confirm Front and Back crops first.');return
        session=copy.copy(self.session)
        if pages is not None:session.pages=list(pages)
        def ready(job):
            self.remember_settings(settings)
            if direct:
                accepted=self.w.hardware.print_job(job,direct=True,driver_color='gray' if settings['color'] in ('gray','mono') else 'color',printer_id=self.printer.currentData())
                if accepted is False:failed('Another print request is active or this job needs review')
            else:self.w.hardware.print_job(job,auto=auto)
        def failed(error):
            self.message.setText('Could not prepare this copy: '+str(error)+'. Originals retained. Adjust Settings and finish again.')
            if direct and self.kind=='copy' and session.pages:
                self.copy_batch=list(session.pages);self.set_active=True;self.simple_mode='set';self.update_copy_actions()
        if direct:self.w.run(lambda:session.job(settings),ready,failed)
        else:self.w.run(lambda:session.job(settings),ready)
    def export(self):
        if self.w.busy:return
        path,_=QFileDialog.getSaveFileName(self,'Export reviewed document',dialog_output(self.w.db,'card-copy.pdf' if self.kind=='nid' else 'document-copy.pdf',self.w.notify),'PDF (*.pdf)')
        if not path:return
        try:
            if Path(path).suffix.lower()!='.pdf':raise ValueError('Choose a .pdf filename; no extension is silently appended')
            path=check_export_target(path,data_root(),self.w.db.conn,[p.source for p in self.session.pages]+self.session.input_paths)
        except ValueError as error:self.message.setText(str(error));return
        settings=self.settings()
        if self.kind=='nid' and (len(self.session.pages)!=2 or any(id(p) not in self.reviewed for p in self.session.pages)):self.message.setText('Confirm both card crops before exporting.');return
        self.w.run(lambda:export_pdf(self.session.job(settings),path),lambda _:self.message.setText('PDF saved. Originals unchanged.'))
    def preview_adjustments(self):
        page=self.current()
        if not page or self.w.busy:return
        settings=self.settings()
        def ready(path):
            from app.ui.canvas import pixmap
            from PySide6.QtWidgets import QDialog
            dialog=QDialog(self);dialog.setWindowTitle('Processed document preview');layout=QVBoxLayout(dialog)
            label=QLabel();label.setPixmap(pixmap(load_image(path,900)));scroll=QScrollArea();scroll.setWidget(label);layout.addWidget(scroll);dialog.resize(850,700);dialog.exec()
        self.w.run(lambda:self.session.prepared(page,settings)[0],ready)
    def export_image(self):
        page=self.current()
        if not page or self.w.busy:return
        if self.kind=='nid' and id(page) not in self.reviewed:self.message.setText('Review and Confirm this card crop first.');return
        path,_=QFileDialog.getSaveFileName(self,'Export processed page',dialog_output(self.w.db,'document.png',self.w.notify),'PNG (*.png);;JPEG (*.jpg *.jpeg)')
        if not path:return
        try:
            if Path(path).suffix.lower() not in ('.png','.jpg','.jpeg'):raise ValueError('Choose a PNG or JPEG extension; none is appended')
            path=check_export_target(path,data_root(),self.w.db.conn,[p.source for p in self.session.pages]+self.session.input_paths)
        except ValueError as error:self.message.setText(str(error));return
        settings=self.settings();self.w.run(lambda:self.session.export_image(page,settings,path),lambda _:self.message.setText('Processed image saved. Original unchanged.'))
    def save_session(self):
        if self.w.busy:return False
        previous=self.session.keep
        try:self.session.keep=True;self.session.manifest(self.settings(),force=True)
        except OSError as error:self.session.keep=previous;self.message.setText('Session could not be saved; edits retained: '+str(error));return False
        self.remember_settings(self.settings());self.dirty=False;self.message.setText('Session kept locally: '+str(self.session.root));return True
    def open_session(self):
        rows=[]
        for path in (data_root()/'document-sessions').glob('*/session.json'):
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data,dict) and data.get('keep') and data.get('kind')==self.kind:rows.append(path)
            except (ValueError,OSError):continue
        if not rows:self.message.setText('No saved document sessions.');return
        labels=[str(p.parent.name) for p in rows];name,ok=QInputDialog.getItem(self,'Open local session','Saved session',labels,0,False)
        if ok and self.before_leave():
            try:
                opened=DocumentSession.open(rows[labels.index(name)]);settings=json.loads(rows[labels.index(name)].read_text())['settings'];self.cleanup_session();self.scan_generation+=1;self.session=opened;self.loading=True
                for key,value in settings.items():
                    if key in self.fields:self.fields[key].setValue(value)
                self.paper.setCurrentText(settings.get('paper','A4'));self.color.setCurrentText(settings.get('color','color'));self.landscape.setChecked(settings.get('landscape',False));self.scale_mode.setCurrentIndex(max(0,self.scale_mode.findData(settings.get('scale_mode','actual'))))
                self.center.setChecked(settings.get('center',self.kind!='nid'));self.quality.blockSignals(True);self.quality.setCurrentIndex(settings.get('quality',0));self.quality.blockSignals(False)
                if self.kind=='nid':self.actual_card.setChecked(settings.get('actual_card',False));self.align.setCurrentText(settings.get('align','center'))
                self.loading=False;self.update_settings_summary();self.reviewed=set();self.dirty=False;self.refresh()
            except (ValueError,OSError,TypeError) as error:self.loading=False;self.message.setText('Session retained; could not open: '+str(error))
    def before_leave(self):
        if self.simple_inflight:self.message.setText('Wait for this scan to finish before leaving.');return False
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Keep this document session?','Save session to keep its scans, discard to clear this temporary session, or cancel navigation.',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if answer==QMessageBox.Save:return self.save_session()
        if answer==QMessageBox.Discard:return self.clear(confirm=False)
        return False
    def clear(self,checked=False,confirm=True):
        if self.w.hardware.operation_active() or self.w.busy:self.message.setText('Wait for active scanning/printing before clearing this session.');return False
        if confirm and self.session.pages and QMessageBox.question(self,'Clear working session','Clear this working session? Explicitly saved sessions and exported PDFs are retained.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return False
        scanner=self.w.hardware.scan_dialog
        if scanner.completion_owner is self:scanner.cancel()
        self.scan_generation+=1;self.delivery_timer.stop();self.pending_delivery=None;self.auto_pending=None;self.simple_pending=None;self.simple_inflight=False;self.set_active=False;self.simple_mode=None;self.copy_batch=[];self.update_copy_actions()
        if self.preview_dialog:self.preview_dialog.close();self.preview_dialog=None
        self.cleanup_session();self.session=DocumentSession(data_root(),self.kind);self.reviewed=set();self.dirty=False;self.refresh();return True
    def cleanup_session(self):
        from app.services.storage import referenced_assets
        try:
            protected=referenced_assets(data_root())
            for job in (self.w.job,getattr(self.w.hardware.print_dialog,'job',None)):
                if job:
                    for photo in job.photos:
                        protected.update(p for layer in photo.layers for p in (layer.source,layer.mask) if p)
            return self.session.cleanup(protected)
        except (ValueError,OSError,TypeError):return False
    def shutdown(self):
        self.scan_generation+=1;self.delivery_timer.stop();self.pending_delivery=None
        try:self.cleanup_session()
        except OSError:pass
