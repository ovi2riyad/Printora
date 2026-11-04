import copy
import json
import os
from pathlib import Path
from PIL import ImageDraw
from PySide6.QtCore import Qt,QThreadPool,QTimer,QUrl,QSize
from PySide6.QtGui import QAction,QKeySequence,QDesktopServices,QIcon
from PySide6.QtWidgets import (QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QListWidget,QListWidgetItem,QStackedWidget,QLabel,QPushButton,QFileDialog,QMessageBox,QLineEdit,QFormLayout,QDoubleSpinBox,QSpinBox,QComboBox,QCheckBox,QColorDialog,QSplitter,QProgressBar,QInputDialog,QAbstractItemView)
from app.core.database import Database,data_root
from app.models.domain import Job,Photo,Layer
from app.services.imaging import import_info,render_photo,remove_background,face_position,resolution_warnings
from app.services.layout import auto_layout,validate_layout
from app.services.pdf import export_pdf,calibration_pdf
from app.ui.workers import Worker
from app.ui.canvas import EditorCanvas,PrintCanvas,pixmap
from app.ui.profiles import Profiles
from app.ui.settings import Settings

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('Studio Photo Maker');self.resize(1450,920);self.setMinimumSize(1100,720)
        self.db=Database();self.job=Job();self.job.print_settings.update({k:self.db.get(k,self.job.print_settings[k]) for k in ('margin','gap_x','gap_y')});self.pool=QThreadPool();self.pool.setMaxThreadCount(1);self.workers=set();self.busy=False;self.dirty=False;self.syncing=False;self.undo=[];self.redo=[];self.preview_version=0;self.thumbnails={};self.source_sizes={}
        self.setAcceptDrops(True)
        root=QWidget();self.setCentralWidget(root);layout=QHBoxLayout(root);layout.setContentsMargins(0,0,0,0)
        self.nav=QListWidget();self.nav.setFixedWidth(205);self.nav.addItems(['Dashboard','New Photo Job','Photo Editor','Joint Photo Maker','Print Composer','Photo Size Profiles','Job History','Settings']);layout.addWidget(self.nav)
        self.stack=QStackedWidget();layout.addWidget(self.stack,1)
        self.dashboard=self.make_dashboard();self.stack.addWidget(self.dashboard)
        self.import_page=self.make_import();self.stack.addWidget(self.import_page)
        self.editor=self.make_editor();self.stack.addWidget(self.editor)
        self.joint_page=self.make_joint();self.stack.addWidget(self.joint_page)
        self.composer=self.make_composer();self.stack.addWidget(self.composer)
        self.profiles=Profiles(self.db,self.refresh_profiles);self.stack.addWidget(self.profiles)
        self.history=QListWidget();self.history.itemDoubleClicked.connect(self.open_history);self.stack.addWidget(self.history)
        self.settings=Settings(self.db,self.run,self.notify,self.apply_theme)
        from PySide6.QtWidgets import QScrollArea
        settings_scroll=QScrollArea();settings_scroll.setWidgetResizable(True);settings_scroll.setWidget(self.settings);self.stack.addWidget(settings_scroll)
        self.nav.currentRowChanged.connect(self.navigate);self.nav.setCurrentRow(0)
        self.progress=QProgressBar();self.progress.setFixedWidth(160);self.progress.setRange(0,0);self.progress.hide();self.statusBar().addPermanentWidget(self.progress)
        for name,shortcut,fn in [('Import images','Ctrl+O',self.import_images),('Save job','Ctrl+S',self.save_job),('New job','Ctrl+N',self.new_job),('Undo','Ctrl+Z',self.undo_edit),('Redo','Ctrl+Y',self.redo_edit),('Export PDF','Ctrl+E',lambda:self.export())]:
            a=QAction(name,self);a.setShortcut(QKeySequence(shortcut));a.triggered.connect(fn);self.addAction(a);self.menuBar().addAction(a)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(180);self.preview_timer.timeout.connect(self.render_preview)
        self.apply_theme();self.refresh_lists();self.notify('Ready · Import images to begin. All processing is local.')

    def button(self,label,fn,layout):
        b=QPushButton(label);b.clicked.connect(fn);layout.addWidget(b);return b
    def page(self,title,subtitle=''):
        w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(24,20,24,20);h=QLabel(title);h.setObjectName('heading');l.addWidget(h)
        if subtitle:s=QLabel(subtitle);s.setWordWrap(True);l.addWidget(s)
        return w,l
    def notify(self,message):self.statusBar().showMessage(message,12000)
    def apply_theme(self):
        dark=self.db.get('theme','Dark')=='Dark';bg='#171c24' if dark else '#eef1f5';panel='#222a36' if dark else '#ffffff';fg='#e8edf5' if dark else '#202735';edge='#364254' if dark else '#ccd3de'
        self.setStyleSheet(f'QWidget {{background:{bg};color:{fg};font-family:Segoe UI;font-size:13px;}} QLabel#heading {{font-size:26px;font-weight:600;padding-bottom:12px;}} QListWidget,QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox {{background:{panel};border:1px solid {edge};border-radius:5px;padding:7px;}} QPushButton {{background:{panel};border:1px solid {edge};border-radius:5px;padding:8px 12px;}} QPushButton:hover {{border-color:#62b6ef;background:#315274;color:white;}} QListWidget::item {{padding:10px;}} QListWidget::item:selected {{background:#285c87;color:white;}} QGraphicsView {{background:#10151c;border:1px solid {edge};}} QCheckBox {{padding:5px;}}')
    def run(self,fn,done):
        if self.busy:self.notify('Please wait for the current operation to finish.');return
        self.busy=True;self.progress.show();self.stack.setEnabled(False);self.nav.setEnabled(False)
        worker=Worker(fn);self.workers.add(worker)
        def finish(value,error=False):
            self.workers.discard(worker);self.busy=False;self.progress.hide();self.stack.setEnabled(True);self.nav.setEnabled(True)
            if error:QMessageBox.warning(self,'Operation failed',value)
            else:
                try:done(value)
                except Exception as e:QMessageBox.warning(self,'Operation failed',str(e))
        worker.signals.done.connect(lambda value:finish(value));worker.signals.error.connect(lambda value:finish(value,True));self.pool.start(worker)
    def navigate(self,index):
        self.stack.setCurrentIndex(index)
        if index in (0,6):self.refresh_history()
        if index==4:self.compose_if_needed()
    def make_dashboard(self):
        w,l=self.page('Studio Photo Maker','Portraits, joint photographs and precise A4 printing — on your own PC.')
        row=QHBoxLayout();l.addLayout(row)
        for label,fn in [('New photo job',self.new_job),('Import images',self.import_images),('Create joint photo',lambda:self.nav.setCurrentRow(3)),('Print composer',lambda:self.nav.setCurrentRow(4))]:self.button(label,fn,row)
        self.summary=QLabel();l.addWidget(self.summary);l.addWidget(QLabel('Recent saved jobs · double-click to reopen'));self.recent=QListWidget();self.recent.itemDoubleClicked.connect(self.open_history);l.addWidget(self.recent)
        l.addWidget(QLabel('Recent exports'));self.exports=QListWidget();self.exports.itemDoubleClicked.connect(lambda item:QDesktopServices.openUrl(QUrl.fromLocalFile(item.text())));l.addWidget(self.exports)
        return w
    def make_import(self):
        w,l=self.page('New photo job','Drop images anywhere in the window, or browse. Original files are never overwritten.')
        self.job_name=QLineEdit(self.job.name);self.job_name.textEdited.connect(self.rename_job);l.addWidget(self.job_name)
        row=QHBoxLayout();l.addLayout(row);self.button('Import photographs',self.import_images,row);self.button('Save job',self.save_job,row);self.button('Remove selected photo',self.remove_photo,row);self.button('Move up',lambda:self.reorder(-1),row);self.button('Move down',lambda:self.reorder(1),row)
        self.photo_list=QListWidget();self.photo_list.setIconSize(QSize(80,80));self.photo_list.currentRowChanged.connect(self.select_photo);self.photo_list.itemDoubleClicked.connect(lambda _:self.nav.setCurrentRow(2));l.addWidget(self.photo_list)
        return w
    def make_editor(self):
        w,l=self.page('Photo editor','Drag the preview to move the selected subject. Use the wheel to zoom. Changes are reversible.')
        split=QSplitter();l.addWidget(split,1);self.canvas=EditorCanvas();self.canvas.moved.connect(self.move_layer);self.canvas.zoomed.connect(self.zoom_layer);split.addWidget(self.canvas)
        tools=QWidget();tools.setMaximumWidth(350);form=QFormLayout(tools)
        self.photo_choice=QComboBox();self.photo_choice.currentIndexChanged.connect(self.select_photo);form.addRow('Photo',self.photo_choice)
        self.layer_choice=QComboBox();self.layer_choice.currentIndexChanged.connect(self.sync_editor);form.addRow('Subject / layer',self.layer_choice)
        self.profile_choice=QComboBox();self.profile_choice.addItems([p['name'] for p in self.db.profiles()]);self.profile_choice.activated.connect(self.apply_profile);form.addRow('Size profile',self.profile_choice)
        self.warning=QLabel();self.warning.setWordWrap(True);self.warning.setStyleSheet('color:#e8b66d');form.addRow(self.warning)
        self.width=self.number(1,1000,45);self.height=self.number(1,1000,55);form.addRow('Width (mm)',self.width);form.addRow('Height (mm)',self.height)
        b=QPushButton('Swap width / height');b.clicked.connect(self.swap_size);form.addRow(b)
        self.qty=QSpinBox();self.qty.setRange(1,10000);self.qty.valueChanged.connect(self.item_changed);form.addRow('Copies',self.qty)
        row=QHBoxLayout()
        for n in (4,6,8,10,12):self.button(str(n),lambda checked=False,v=n:self.qty.setValue(v),row)
        form.addRow(row)
        self.bg=QPushButton('Choose background');self.bg.clicked.connect(lambda:self.pick_color('background'));form.addRow(self.bg)
        row=QHBoxLayout()
        for label,color in [('Blue','#ADD8E6'),('White','#FFFFFF'),('Gray','#D3D3D3')]:self.button(label,lambda checked=False,c=color:self.set_bg(c),row)
        form.addRow(row)
        self.border=QCheckBox('Border enabled');self.border.toggled.connect(self.item_changed);form.addRow(self.border)
        self.border_mm=self.number(0,10,.2);form.addRow('Border (mm)',self.border_mm)
        b=QPushButton('Border color');b.clicked.connect(lambda:self.pick_color('border_color'));form.addRow(b)
        self.scale=self.number(.05,8,1,.05);self.x=self.number(-3,4,.5,.02);self.y=self.number(-3,4,.5,.02);self.rotation=self.number(-180,180,0,1)
        for label,widget in [('Subject scale',self.scale),('Horizontal position',self.x),('Vertical position',self.y),('Rotation (degrees)',self.rotation)]:form.addRow(label,widget)
        self.erosion=self.number(-8,8,0,1);self.feather=self.number(0,8,0,.25);form.addRow('Edge contract / expand',self.erosion);form.addRow('Edge feather (pixels)',self.feather)
        for label,fn in [('Remove selected background',self.remove_bg),('Keep original background',self.original_bg),('Detect & position face',self.auto_face),('Reset selected crop',self.reset_crop),('Undo',self.undo_edit),('Redo',self.redo_edit),('Export composed photo',self.export_image)]:
            b=QPushButton(label);b.clicked.connect(fn);form.addRow(b)
        self.before=QCheckBox('Before preview (original backgrounds)');self.before.toggled.connect(self.schedule_preview);form.addRow(self.before)
        # A scroll area keeps the full tool panel usable at smaller desktop resolutions.
        from PySide6.QtWidgets import QScrollArea
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(tools);scroll.setMinimumWidth(340);split.addWidget(scroll);split.setSizes([850,350])
        return w
    def number(self,low,high,value,step=.1):
        n=QDoubleSpinBox();n.setDecimals(2);n.setRange(low,high);n.setSingleStep(step);n.setValue(value);n.valueChanged.connect(self.item_changed);return n
    def make_joint(self):
        w,l=self.page('Joint Photo Maker','Combine 2–4 cut-out subjects on one common background. An already-combined photograph can be imported as one layer.')
        row=QHBoxLayout();l.addLayout(row);self.button('Create from separate portraits',self.create_joint,row);self.button('Import already-combined photo',lambda:self.import_images(combined=True),row)
        self.joint_list=QListWidget();l.addWidget(self.joint_list);self.joint_list.currentRowChanged.connect(self.select_joint)
        row=QHBoxLayout();l.addLayout(row)
        for label,fn in [('Open in editor',lambda:self.nav.setCurrentRow(2)),('Add person',self.add_person),('Remove person',self.remove_person),('Replace person',self.replace_person),('Bring forward',lambda:self.layer_order(1)),('Send backward',lambda:self.layer_order(-1)),('Reset composition',self.reset_joint)]:self.button(label,fn,row)
        l.addWidget(QLabel('Select a composition, then choose a subject in Photo Editor to adjust scale, crop, position, edges and rotation.\nSeparate portraits are masked before being added. Save job preserves all editable layers.'))
        return w
    def make_composer(self):
        w,l=self.page('A4 print composer','Drag photos to reposition on a 0.5 mm grid. Dashed lines show margins. Export checks boundaries and overlaps.')
        row=QHBoxLayout();l.addLayout(row)
        self.landscape=QCheckBox('A4 landscape');row.addWidget(self.landscape)
        self.margin=QDoubleSpinBox();self.margin.setRange(0,80);self.margin.setValue(self.db.get('margin',10));row.addWidget(QLabel('Margins mm'));row.addWidget(self.margin)
        self.gap_x=QDoubleSpinBox();self.gap_x.setRange(0,50);self.gap_x.setValue(self.db.get('gap_x',2));row.addWidget(QLabel('Horizontal gap'));row.addWidget(self.gap_x)
        self.gap_y=QDoubleSpinBox();self.gap_y.setRange(0,50);self.gap_y.setValue(self.db.get('gap_y',3));row.addWidget(QLabel('Vertical gap'));row.addWidget(self.gap_y)
        self.guides=QCheckBox('Cut guides');row.addWidget(self.guides)
        for widget in (self.landscape,self.guides):widget.toggled.connect(self.print_changed)
        for widget in (self.margin,self.gap_x,self.gap_y):widget.valueChanged.connect(self.print_changed)
        row=QHBoxLayout();l.addLayout(row)
        self.button('Automatic / reset layout',self.auto_compose,row);self.button('Center page rows',self.center_page,row)
        self.page_choice=QComboBox();self.page_choice.currentIndexChanged.connect(self.preview_print);row.addWidget(self.page_choice)
        self.button('Add page',self.add_page,row);self.button('Remove empty page',self.remove_page,row)
        self.button('Move selected to page…',self.move_to_page,row)
        self.print_canvas=PrintCanvas();self.print_canvas.changed.connect(self.manual_layout_changed);l.addWidget(self.print_canvas,1)
        row=QHBoxLayout();l.addLayout(row);self.button('Export all pages PDF',lambda:self.export(),row);self.button('Export current page PDF',lambda:self.export(True),row);self.button('Calibration PDF',self.calibration,row)
        self.open_folder=QCheckBox('Open output folder');self.open_folder.setChecked(True);row.addWidget(self.open_folder)
        l.addWidget(QLabel('Print at Actual Size / 100%. Avoid Fit to Page. Check printable margins for your printer.'))
        return w

    def current_photo(self):
        i=self.photo_choice.currentIndex();return self.job.photos[i] if 0<=i<len(self.job.photos) else None
    def current_layer(self):
        p=self.current_photo();i=self.layer_choice.currentIndex();return p.layers[i] if p and 0<=i<len(p.layers) else None
    def checkpoint(self):
        self.undo.append(copy.deepcopy(self.job.to_dict()));self.undo=self.undo[-50:];self.redo.clear();self.mark_dirty()
    def mark_dirty(self):self.dirty=True
    def changed_content(self):
        self.job.placements=[];self.mark_dirty();self.schedule_preview()
    def select_photo(self,index):
        if self.syncing or not 0<=index<len(self.job.photos):return
        self.syncing=True;self.photo_choice.setCurrentIndex(index);self.photo_list.setCurrentRow(index);self.syncing=False
        self.layer_choice.blockSignals(True);self.layer_choice.clear();self.layer_choice.addItems([f'{i+1} · {Path(s.source).name}' for i,s in enumerate(self.job.photos[index].layers)]);self.layer_choice.blockSignals(False);self.layer_choice.setCurrentIndex(0);self.sync_editor()
    def sync_editor(self,*_):
        p=self.current_photo();s=self.current_layer()
        if not p:return
        self.syncing=True
        for w,v in [(self.width,p.width),(self.height,p.height),(self.qty,p.quantity),(self.border_mm,p.border_mm)]:w.setValue(v)
        self.border.setChecked(p.border);self.profile_choice.setCurrentText(p.profile);self.bg.setText('Background '+p.background)
        if s:
            for w,v in [(self.scale,s.scale),(self.x,s.x),(self.y,s.y),(self.rotation,s.rotation),(self.erosion,s.erosion),(self.feather,s.feather)]:w.setValue(v)
        profile=next((x for x in self.db.profiles() if x['name']==p.profile),{})
        self.warning.setText(profile.get('notes','')+'\n'+profile.get('url','') if profile.get('country') else '')
        self.syncing=False;self.schedule_preview()
    def item_changed(self,*_):
        if self.syncing:return
        p=self.current_photo();s=self.current_layer()
        if not p:return
        self.checkpoint();p.width=self.width.value();p.height=self.height.value();p.quantity=self.qty.value();p.border=self.border.isChecked();p.border_mm=self.border_mm.value()
        if s:s.scale=self.scale.value();s.x=self.x.value();s.y=self.y.value();s.rotation=self.rotation.value();s.erosion=round(self.erosion.value());s.feather=self.feather.value()
        self.changed_content()
    def schedule_preview(self,*_):
        if hasattr(self,'preview_timer'):self.preview_timer.start()
    def render_preview(self):
        if self.stack.currentIndex()==4:return
        p=self.current_photo()
        if not p:return
        if self.busy:self.preview_timer.start(200);return
        photo=copy.deepcopy(p);before=self.before.isChecked()
        def render():
            im=render_photo(photo,130,before)
            if photo.border and photo.border_mm and not before:
                d=ImageDraw.Draw(im);b=max(1,round(photo.border_mm/25.4*130));d.rectangle((0,0,im.width-1,im.height-1),outline=photo.border_color,width=b)
            return im
        self.run(render,lambda im:self.canvas.display(im))
    def move_layer(self,dx,dy):
        s=self.current_layer()
        if s:self.checkpoint();s.x+=dx;s.y+=dy;self.changed_content();self.sync_editor()
    def zoom_layer(self,factor):
        s=self.current_layer()
        if s:self.checkpoint();s.scale=max(.05,min(8,s.scale*factor));self.changed_content();self.sync_editor()
    def swap_size(self):
        if self.current_photo():self.checkpoint();self.current_photo().swap();self.changed_content();self.sync_editor()
    def apply_profile(self):
        p=self.current_photo();profile=next((x for x in self.db.profiles() if x['name']==self.profile_choice.currentText()),None)
        if p and profile:
            self.checkpoint();p.profile=profile['name'];p.width=profile['width'];p.height=profile['height'];p.background=profile.get('background','#ADD8E6');p.border=profile.get('border',True);p.border_color=profile.get('border_color','#808080');p.border_mm=profile.get('border_mm',.2);self.changed_content();self.sync_editor()
    def set_bg(self,color):
        if self.current_photo():self.checkpoint();self.current_photo().background=color;self.changed_content();self.sync_editor()
    def pick_color(self,field):
        p=self.current_photo()
        if p:
            from PySide6.QtGui import QColor
            color=QColorDialog.getColor(QColor(getattr(p,field)),self)
            if color.isValid():self.checkpoint();setattr(p,field,color.name());self.changed_content();self.sync_editor()
    def reset_crop(self):
        s=self.current_layer()
        if s:self.checkpoint();s.x=s.y=.5;s.scale=1;s.rotation=0;self.changed_content();self.sync_editor()
    def original_bg(self):
        s=self.current_layer()
        if s:self.checkpoint();s.mask='';self.changed_content();self.sync_editor()
    def remove_bg(self):
        s=self.current_layer()
        if s:
            self.checkpoint()
            model_dir=self.db.get('model_dir',str(data_root()/'models'))
            def done(path):s.mask=path;self.changed_content();self.sync_editor()
            self.run(lambda:remove_background(s.source,model_dir,data_root()/'cache'),done)
    def auto_face(self):
        p=self.current_photo();s=self.current_layer()
        if s:
            self.checkpoint()
            def done(layer):s.__dict__.update(layer.__dict__);self.changed_content();self.sync_editor()
            self.run(lambda:face_position(copy.deepcopy(s),p.width,p.height),done)
    def undo_edit(self):
        if not self.undo or self.busy:return
        self.redo.append(self.job.to_dict());self.job=Job.from_dict(self.undo.pop());self.dirty=True;self.refresh_lists()
    def redo_edit(self):
        if not self.redo or self.busy:return
        self.undo.append(self.job.to_dict());self.job=Job.from_dict(self.redo.pop());self.dirty=True;self.refresh_lists()

    def import_images(self,checked=False,combined=False,paths=None):
        if self.busy:return
        if paths is None:paths,_=QFileDialog.getOpenFileNames(self,'Import photographs','','Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)')
        if not paths:return
        def read():
            valid=[];errors=[]
            for path in paths:
                try:valid.append(import_info(path))
                except Exception as e:errors.append(f'{Path(path).name}: {e}')
            return valid,errors
        def done(result):
            valid,errors=result;self.checkpoint()
            for path,size,thumb in valid:
                self.thumbnails[path]=thumb;self.source_sizes[path]=size
                p=self.new_photo(Path(path).stem,'Combined joint' if combined else 'Individual');p.layers=[Layer(path)];self.job.photos.append(p)
            self.changed_content();self.refresh_lists();self.nav.setCurrentRow(1)
            if errors:QMessageBox.warning(self,'Some images were not imported','\n'.join(errors))
        self.run(read,done)
    def new_photo(self,name,kind):
        profile_name=self.db.get('joint_profile','Studio Joint Photo') if kind!='Individual' else self.db.get('default_profile','Studio Portrait')
        profile=next((p for p in self.db.profiles() if p['name']==profile_name),{})
        return Photo(name=name,kind=kind,profile=profile_name,width=profile.get('width',55 if kind!='Individual' else 45),height=profile.get('height',45 if kind!='Individual' else 55),quantity=self.db.get('quantity',4),background=self.db.get('background','#ADD8E6'),border=self.db.get('border',True),border_color=self.db.get('border_color','#808080'),border_mm=self.db.get('border_mm',.2))
    def refresh_lists(self):
        previous=self.photo_choice.currentIndex();self.syncing=True;self.photo_list.clear();self.photo_choice.clear();self.joint_list.clear();self.joint_ids=[]
        for p in self.job.photos:
            text=f'{p.name} · {p.width:g} × {p.height:g} mm · {p.quantity} copies';item=QListWidgetItem(text)
            if p.layers:
                path=p.layers[0].source
                if path in self.thumbnails:item.setIcon(QIcon(pixmap(self.thumbnails[path])))
                if path in self.source_sizes:
                    sw,sh=self.source_sizes[path];item.setText(text+f' · source {sw} × {sh} px')
                item.setToolTip(path)
                if not Path(path).exists():item.setText(text+' · SOURCE MISSING')
            self.photo_list.addItem(item);self.photo_choice.addItem(p.name)
            if p.kind!='Individual':self.joint_ids.append(p.id);self.joint_list.addItem(text)
        self.job_name.setText(self.job.name);self.syncing=False
        if self.job.photos:self.select_photo(max(0,min(previous,len(self.job.photos)-1)))
        else:
            self.canvas.scene().clear();self.layer_choice.clear();self.warning.clear()
        self.refresh_history()
    def refresh_profiles(self):
        text=self.profile_choice.currentText();self.profile_choice.clear();self.profile_choice.addItems([p['name'] for p in self.db.profiles()]);self.profile_choice.setCurrentText(text)
        country=self.profiles.country.currentText();self.profiles.country.blockSignals(True);self.profiles.country.clear();self.profiles.country.addItems(['All countries']+sorted({p.get('country','') for p in self.db.profiles() if p.get('country')}));self.profiles.country.setCurrentText(country);self.profiles.country.blockSignals(False)
        if hasattr(self,'settings'):
            for key in ('default_profile','joint_profile'):
                widget=self.settings.fields[key];value=widget.currentText();widget.clear();widget.addItems([p['name'] for p in self.db.profiles()]);widget.setCurrentText(value)
    def remove_photo(self):
        i=self.photo_list.currentRow()
        if i>=0:self.checkpoint();self.job.photos.pop(i);self.changed_content();self.refresh_lists()
    def reorder(self,delta):
        i=self.photo_list.currentRow();j=i+delta
        if 0<=i<len(self.job.photos) and 0<=j<len(self.job.photos):self.checkpoint();self.job.photos[i],self.job.photos[j]=self.job.photos[j],self.job.photos[i];self.changed_content();self.refresh_lists();self.select_photo(j)
    def rename_job(self,text):self.job.name=text;self.mark_dirty()
    def save_job(self):
        if self.busy:return
        try:self.db.save_job(self.job);self.dirty=False;self.refresh_history();self.notify('Job saved locally.')
        except Exception as e:QMessageBox.warning(self,'Save failed',str(e))
    def save_before_close(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved job','Save changes to this job?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
        if answer==QMessageBox.Cancel:return False
        if answer==QMessageBox.Save:self.save_job();return not self.dirty
        return True
    def new_job(self):
        if self.busy or not self.save_before_close():return
        self.job=Job();self.job.print_settings.update({k:self.db.get(k,self.job.print_settings[k]) for k in ('margin','gap_x','gap_y')});self.undo.clear();self.redo.clear();self.thumbnails.clear();self.source_sizes.clear();self.dirty=False;self.canvas.scene().clear();self.sync_print_controls();self.refresh_lists();self.nav.setCurrentRow(1)
    def refresh_history(self):
        for listing in (self.recent,self.history):
            listing.clear()
            for id,name,date in self.db.jobs():
                item=QListWidgetItem(f'{name}   ·   {date}');item.setData(Qt.UserRole,id);listing.addItem(item)
        self.summary.setText(f'{len(self.job.photos)} photographs in this order   ·   {sum(p.quantity for p in self.job.photos)} copies   ·   {len(self.db.profiles())} saved size profiles')
        self.exports.clear()
        for row in self.db.conn.execute('SELECT path FROM exports ORDER BY created DESC LIMIT 10'):self.exports.addItem(row[0])
    def open_history(self,item):
        if self.busy or not self.save_before_close():return
        try:
            self.job=self.db.load_job(item.data(Qt.UserRole));self.undo.clear();self.redo.clear();self.thumbnails.clear();self.source_sizes.clear();self.dirty=False;self.sync_print_controls();self.refresh_lists();self.nav.setCurrentRow(1);self.load_thumbnails()
        except Exception as e:QMessageBox.warning(self,'Cannot open job',str(e))
    def load_thumbnails(self):
        paths={layer.source for p in self.job.photos for layer in p.layers}
        def read():
            result=[]
            for path in paths:
                try:result.append(import_info(path))
                except Exception:pass
            return result
        def done(rows):
            for path,size,thumb in rows:self.thumbnails[path]=thumb;self.source_sizes[path]=size
            self.refresh_lists()
        self.run(read,done)
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
    def dropEvent(self,e):self.import_images(paths=[u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def create_joint(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Choose two to four people','','Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)')
        if not paths:return
        if not 2<=len(paths)<=4:QMessageBox.information(self,'Joint photo','Choose between two and four individual photographs.');return
        model_dir=self.db.get('model_dir',str(data_root()/'models'))
        def process():
            layers=[]
            for i,path in enumerate(paths):
                source,_,_=import_info(path);mask=remove_background(source,model_dir,data_root()/'cache');layers.append(Layer(source,mask,x=(i+.5)/len(paths),scale=.68))
            return layers
        def done(layers):
            self.checkpoint();p=self.new_photo('Joint photograph','Joint composition');p.layers=layers;self.job.photos.append(p);self.changed_content();self.refresh_lists();self.select_photo(len(self.job.photos)-1);self.nav.setCurrentRow(2)
        self.run(process,done)
    def select_joint(self,i):
        if 0<=i<len(self.joint_ids):
            id=self.joint_ids[i]
            for j,p in enumerate(self.job.photos):
                if p.id==id:self.select_photo(j);break
    def add_person(self):
        p=self.current_photo()
        if not p or p.kind=='Individual':self.notify('Select a joint composition first.');return
        if len(p.layers)>=4:self.notify('A composition supports up to four people.');return
        path,_=QFileDialog.getOpenFileName(self,'Add person','','Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)')
        if path:
            model_dir=self.db.get('model_dir',str(data_root()/'models'))
            def done(mask):self.checkpoint();p.layers.append(Layer(path,mask,scale=.68));self.changed_content();self.refresh_lists();self.nav.setCurrentRow(2)
            self.run(lambda:remove_background(path,model_dir,data_root()/'cache'),done)
    def remove_person(self):
        p=self.current_photo();i=self.layer_choice.currentIndex()
        if p and p.kind!='Individual' and len(p.layers)>1 and i>=0:self.checkpoint();p.layers.pop(i);self.changed_content();self.refresh_lists()
    def replace_person(self):
        s=self.current_layer()
        if not s:return
        path,_=QFileDialog.getOpenFileName(self,'Replace subject','','Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)')
        if path:
            model_dir=self.db.get('model_dir',str(data_root()/'models'));masked=bool(s.mask)
            def process():import_info(path);return remove_background(path,model_dir,data_root()/'cache') if masked else ''
            def done(mask):self.checkpoint();s.source=path;s.mask=mask;self.changed_content();self.refresh_lists()
            self.run(process,done)
    def layer_order(self,delta):
        p=self.current_photo();i=self.layer_choice.currentIndex();j=i+delta
        if p and 0<=i<len(p.layers) and 0<=j<len(p.layers):self.checkpoint();p.layers[i],p.layers[j]=p.layers[j],p.layers[i];self.changed_content();self.refresh_lists();self.layer_choice.setCurrentIndex(j)
    def reset_joint(self):
        p=self.current_photo()
        if p and p.kind!='Individual':
            self.checkpoint()
            for i,s in enumerate(p.layers):s.x=(i+.5)/len(p.layers);s.y=.5;s.scale=.68 if len(p.layers)>1 else 1;s.rotation=0
            self.changed_content();self.sync_editor()
    def export_image(self):
        p=self.current_photo()
        if not p:return
        path,_=QFileDialog.getSaveFileName(self,'Save composed photograph',str(Path(self.db.get('output',str(Path.home()/'Documents')))/(p.name+'.png')),'PNG (*.png)')
        if path:
            source_paths={Path(s.source).resolve() for x in self.job.photos for s in x.layers}
            if Path(path).resolve() in source_paths:QMessageBox.warning(self,'Original protected','Choose a different filename from any imported source.');return
            photo=copy.deepcopy(p)
            dpi=self.db.get('dpi',300)
            def write():
                im=render_photo(photo,dpi)
                if photo.border:
                    b=round(photo.border_mm/25.4*dpi)
                    if b:ImageDraw.Draw(im).rectangle((0,0,im.width-1,im.height-1),outline=photo.border_color,width=b)
                im.save(path,dpi=(dpi,)*2);return path
            self.run(write,lambda result:self.notify('Saved '+result))

    def sync_print_controls(self):
        self.syncing=True;s=self.job.print_settings;self.landscape.setChecked(s['landscape']);self.margin.setValue(s['margin']);self.gap_x.setValue(s['gap_x']);self.gap_y.setValue(s['gap_y']);self.guides.setChecked(s['guides']);self.syncing=False
    def print_changed(self,*_):
        if self.syncing:return
        self.job.print_settings=dict(landscape=self.landscape.isChecked(),margin=self.margin.value(),gap_x=self.gap_x.value(),gap_y=self.gap_y.value(),guides=self.guides.isChecked());self.job.placements=[];self.mark_dirty();self.auto_compose()
    def compose_if_needed(self):
        if not self.job.placements:self.auto_compose()
        else:self.update_pages();self.preview_print()
    def auto_compose(self):
        try:
            self.job.placements=auto_layout(self.job.photos,self.job.print_settings);self.job.page_count=max([p.page+1 for p in self.job.placements],default=1);self.mark_dirty();self.update_pages();self.preview_print()
        except Exception as e:QMessageBox.warning(self,'Layout cannot fit',str(e))
    def update_pages(self):
        i=self.page_choice.currentIndex();self.page_choice.blockSignals(True);self.page_choice.clear();self.page_choice.addItems([f'Page {n+1} / {self.job.page_count}' for n in range(self.job.page_count)]);self.page_choice.setCurrentIndex(max(0,min(i,self.job.page_count-1)));self.page_choice.blockSignals(False)
    def preview_print(self,*_):
        if self.busy:
            QTimer.singleShot(200,self.preview_print);return
        snapshot=copy.deepcopy(self.job);page=max(0,self.page_choice.currentIndex());ids={r.photo_id for r in snapshot.placements if r.page==page}
        def render():
            result={}
            for p in snapshot.photos:
                if p.id not in ids:continue
                im=render_photo(p,100)
                if p.border and p.border_mm:
                    b=max(1,round(p.border_mm/25.4*100));ImageDraw.Draw(im).rectangle((0,0,im.width-1,im.height-1),outline=p.border_color,width=b)
                result[p.id]=im
            return result
        self.run(render,lambda images:self.print_canvas.display(self.job,page,images))
    def add_page(self):self.job.page_count+=1;self.mark_dirty();self.update_pages();self.page_choice.setCurrentIndex(self.job.page_count-1)
    def manual_layout_changed(self):
        self.mark_dirty();self.preview_print()
    def remove_page(self):
        page=self.page_choice.currentIndex()
        if self.job.page_count<=1:return
        if any(p.page==page for p in self.job.placements):self.notify('Move all photos off this page before removing it.');return
        for p in self.job.placements:
            if p.page>page:p.page-=1
        self.job.page_count-=1;self.mark_dirty();self.update_pages();self.preview_print()
    def move_to_page(self):
        items=[i for i in self.print_canvas.scene().selectedItems() if hasattr(i,'r')]
        if not items:return
        page,ok=QInputDialog.getInt(self,'Move photograph','Destination page',1,1,self.job.page_count)
        if ok:
            for item in items:item.r.page=page-1
            self.mark_dirty();self.preview_print()
    def center_page(self):
        page=self.page_choice.currentIndex();rows={}
        from app.services.layout import page_size
        pw,_=page_size(self.job.print_settings)
        for r in self.job.placements:
            if r.page==page:rows.setdefault(round(r.y,1),[]).append(r)
        for row in rows.values():
            left=min(r.x for r in row);right=max(r.x+r.width for r in row);shift=(pw-(right-left))/2-left
            for r in row:r.x+=shift
        self.mark_dirty();self.preview_print()
    def export(self,current=False):
        if self.busy:return
        if not self.job.placements:self.auto_compose();self.notify('Layout prepared. Review it, then export.');return
        try:validate_layout(self.job)
        except Exception as e:QMessageBox.warning(self,'Invalid layout',str(e));return
        path,_=QFileDialog.getSaveFileName(self,'Export print PDF',str(Path(self.db.get('output',str(Path.home()/'Documents')))/(self.job.name.replace('/','-').replace('\\','-')+'.pdf')),'PDF (*.pdf)')
        if not path:return
        if not self.output_safe(path):return
        snapshot=copy.deepcopy(self.job);page=self.page_choice.currentIndex() if current else None;dpi=self.db.get('dpi',300)
        def process():
            warnings=[]
            for p in snapshot.photos:warnings.extend(resolution_warnings(p))
            return warnings
        def checked(warnings):
            if warnings and QMessageBox.question(self,'Low image resolution','\n'.join(warnings)+'\n\nExport anyway?')!=QMessageBox.Yes:return
            def done(result):
                with self.db.conn:self.db.conn.execute('INSERT INTO exports(path) VALUES(?)',(result,))
                self.save_job();self.notify('PDF exported. Print at Actual Size / 100%.')
                if self.open_folder.isChecked():QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result).parent)))
            self.run(lambda:export_pdf(snapshot,path,page,dpi),done)
        self.run(process,checked)
    def calibration(self):
        path,_=QFileDialog.getSaveFileName(self,'Calibration PDF','calibration.pdf','PDF (*.pdf)')
        if path and self.output_safe(path):self.run(lambda:calibration_pdf(path),lambda p:QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
    def output_safe(self,path):
        protected={Path(s.source).resolve() for p in self.job.photos for s in p.layers}
        protected.update(Path(s.mask).resolve() for p in self.job.photos for s in p.layers if s.mask)
        if Path(path).resolve() in protected:
            QMessageBox.warning(self,'Original protected','Choose an output filename different from all source photographs and masks.');return False
        return True
    def closeEvent(self,e):
        if self.busy:self.notify('Wait for the current operation to finish before closing.');e.ignore();return
        if not self.save_before_close():e.ignore();return
        self.preview_timer.stop();self.pool.waitForDone();self.db.conn.close();e.accept()
