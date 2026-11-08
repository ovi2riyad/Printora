"""Focused portrait/joint print workflows, with the same physical-size services."""
from app.services.user_folders import dialog_folder,dialog_output
import copy
import math
import sys
from pathlib import Path
from PIL import Image,ImageDraw
from PySide6.QtCore import Qt,QTimer,QThreadPool,QUrl,QProcess,QSize
from PySide6.QtGui import QAction,QColor,QDesktopServices,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QStackedWidget,QFrame,QScrollArea,QDoubleSpinBox,QSpinBox,QComboBox,QCheckBox,QFileDialog,QColorDialog,QMessageBox,QProgressBar,QDialog,QListWidget,QDialogButtonBox,QTabWidget,QButtonGroup,QSizePolicy,QToolButton)
from app.core.database import Database,data_root
from app.models.domain import Photo,Layer,Job
from app.services.imaging import import_info,face_position,remove_background,render_photo,find_background_model,resolution_warnings,prepare_layer,render_bordered_photo,export_photo_image
from app.services.framing import frame_photo,align_layers
from app.services.layout import auto_layout,validate_layout,page_size,layout_capacity,resize_copies
from app.services.profiles import normalize_profile,apply_profile
from app.ui.profiles import Profiles
from app.ui.print_options import PrintOptions
from app.services.pdf import export_pdf
from app.ui.workers import Worker
from app.ui.canvas import EditorCanvas,PrintCanvas
from app.ui.studio_settings import StudioSettings as Settings
from app.services.storage import prepare_restore,install_restore,discard_restore
from app.services.cropping import CropTray
from app.ui.cropper import Cropper,PreparedPicker
from app.ui.transform_canvas import TransformCanvas
from app.services.record_recovery import recoverable_record,checked_document
from app.ui.panels import AdaptivePanel,splitter
from app.services.user_folders import folder,output_path

class WorkspaceStack(QStackedWidget):
    """Inactive settings/library pages must not set every workspace's minimum size."""
    def __init__(self):
        from PySide6.QtWidgets import QLayout
        super().__init__();self.layout().setSizeConstraint(QLayout.SetNoConstraint);self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Ignored);self.currentChanged.connect(self.current_minimum)
    def current_minimum(self,*_):
        self.setMinimumSize(self.minimumSizeHint().expandedTo(QSize(0,0)));self.updateGeometry()
    def minimumSizeHint(self):
        current=self.currentWidget();return current.minimumSizeHint() if current else QSize(0,0)
    def sizeHint(self):
        current=self.currentWidget();return current.sizeHint() if current else QSize(0,0)

class StudioWindow(QMainWindow):
    def __init__(self):
        from app.version import VERSION
        super().__init__();self.setWindowTitle(f'Printora {VERSION} — Studio Photo Maker');self.resize(1360,900);self.setMinimumSize(1050,740)
        screen=QApplication.primaryScreen()
        if screen:
            available=screen.availableGeometry();width=max(1,available.width()-20);height=max(1,available.height()-50)
            self.setMinimumSize(min(1050,width),min(740,height));self.resize(min(1360,width),min(900,height))
        icon=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'assets'/'Printora.ico'
        if icon.is_file():self.setWindowIcon(QIcon(str(icon)))
        self.db=Database();self.job=Job();self.photo=None;self.mode='portrait';self.dirty=False;self.busy=False;self.syncing=False;self.workers=set();self.undo=[];self.redo=[];self.tray=CropTray(root=data_root()/'library')
        self.pool=QThreadPool();self.pool.setMaxThreadCount(1);self.setAcceptDrops(True)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(160);self.timer.timeout.connect(self.render_preview)
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(30,20,30,20);layout.setSpacing(18)
        header=QHBoxLayout();brand=QLabel('STUDIO  /  PHOTO MAKER');brand.setObjectName('brand');header.addWidget(brand);header.addStretch()
        self.home_button=self.button('Dashboard',self.home);header.addWidget(self.home_button);self.button('Cropper / library',self.open_cropper,header);self.button('Photo profiles',self.profiles_dialog,header);self.button('Save job',self.save_job,header);self.button('Saved jobs',self.open_jobs,header);self.button('Settings',self.settings_dialog,header);layout.addLayout(header)
        self.stack=WorkspaceStack();layout.addWidget(self.stack,1);self.stack.addWidget(self.dashboard());self.stack.addWidget(self.workspace());self.stack.addWidget(self.print_page())
        self.cropper=Cropper(self.tray,self.run,self.notify,self.use_crops,db=self.db);self.stack.addWidget(self.cropper)
        footer=QHBoxLayout();self.status=QLabel('Ready. All photographs stay on this PC.');self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);self.status.setMaximumHeight(38);self.status.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);footer.addWidget(self.status,1);self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setFixedWidth(140);self.progress.hide();footer.addWidget(self.progress);layout.addLayout(footer)
        for title,key,fn in [('Import','Ctrl+O',self.import_to_cropper),('Save','Ctrl+S',self.save_job),('Undo','Ctrl+Z',self.undo_edit),('Redo','Ctrl+Shift+Z',self.redo_edit),('Redo','Ctrl+Y',self.redo_edit),('Transform','Ctrl+T',lambda:self.canvas.set_tool('move')),('Fit view','Ctrl+0',self.canvas.fit_preview),('100%','Ctrl+1',self.canvas.resetTransform)]:
            action=QAction(title,self);action.setShortcut(key);action.triggered.connect(fn);self.addAction(action)
        self._save_generation=0;self._autosave_callback=None;self._save_prompt_active=False
        self.autosave=QTimer(self);self.autosave.setSingleShot(True);self.autosave.setInterval(2200);self.apply_theme()
        from app.ui.studio_manager import StudioManager
        self.studio=StudioManager(self)
        from app.ui.shell import StudioShell
        self.shell=StudioShell(self)
        workflow=self.db.get('default_workflow','dashboard')
        if self.db.preference_diagnostics:
            keys=', '.join(d['key'] for d in self.db.preference_diagnostics)
            self.notify('Recovered optional preferences: '+keys+'. Original values are retained in studio.db / config; other data is unchanged.')
        if workflow!='dashboard':QTimer.singleShot(0,lambda:self.open_cropper() if workflow=='cropper' else self.start_workflow(workflow) if workflow in ('portrait','joint') else None)

    def button(self,text,fn,layout=None,primary=False):
        from app.ui.buttons import WrappingButton
        b=WrappingButton(text);b.clicked.connect(fn)
        if primary:b.setObjectName('primary')
        if layout is not None:layout.addWidget(b)
        return b
    def title(self,text,layout,sub=None):
        label=QLabel(text);label.setObjectName('title');label.setWordWrap(True);layout.addWidget(label)
        if sub:
            label=QLabel(sub);label.setObjectName('muted');label.setWordWrap(True);layout.addWidget(label)
    def dashboard(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(30,45,30,45);layout.setSpacing(16)
        self.title('Prepare first. Then print.',layout,'Start in Cropper to separate photos from a scan sheet or camera image. Choose your prepared photos in either maker.')
        row=QHBoxLayout();row.setSpacing(24);layout.addLayout(row,1)
        for mode,title,detail,size in [('cropper','Cropper','Import scan sheets or phone photos. Separate, straighten and keep crops in your library.','One source can contain several portraits'),('portrait','Portrait print','Choose one prepared photo. Refine framing and print on a clean background.','42 × 52 mm studio preset · editable profiles'),('joint','Joint photo print','Choose an existing couple photo or two portraits. Keep the group together or adjust separate layers.','55 × 45 mm studio preset · editable profiles')]:
            card=QFrame();card.setObjectName('card');c=QVBoxLayout(card);c.setContentsMargins(30,35,30,35);c.setSpacing(18)
            self.title(title,c,detail);label=QLabel(size);label.setWordWrap(True);label.setObjectName('muted');c.addWidget(label);c.addStretch();self.button('Open cropper  →' if mode=='cropper' else 'Start '+title.lower()+'  →',lambda checked=False,m=mode:self.open_cropper() if m=='cropper' else self.start_workflow(m),c,True);row.addWidget(card)
        layout.addWidget(QLabel('Exact millimetre sizes  ·  Local background removal  ·  A4 PDF output'))
        return page
    def section(self,layout,text):
        label=QLabel(text);label.setWordWrap(True);label.setObjectName('section');layout.addWidget(label)
    def spin(self,low,high,value,step=.1):
        w=QDoubleSpinBox();w.setRange(low,high);w.setDecimals(2);w.setSingleStep(step);w.setValue(value);w.valueChanged.connect(self.controls_changed);return w
    def pair(self,layout,label,widget):
        row=QHBoxLayout();caption=QLabel(label);caption.setWordWrap(True);row.addWidget(caption);row.addStretch();row.addWidget(widget);layout.addLayout(row)
    def workspace(self):
        from app.ui.preview_workspace import CompactEditorPage
        page=CompactEditorPage(self);outer=QVBoxLayout(page);outer.setContentsMargins(0,0,0,0);outer.setSpacing(4)
        self.editor_actions=QHBoxLayout();outer.addLayout(self.editor_actions)
        self.workflow_title=QLabel('Portrait print');self.workflow_title.setObjectName('section');self.editor_actions.addWidget(self.workflow_title)
        self.choose_photo_button=self.button('Choose photo',self.choose_prepared,self.editor_actions,True);self.editor_actions.addStretch()
        self.subject=QComboBox();self.subject.currentIndexChanged.connect(self.sync_controls)
        self.guide=QCheckBox('Positioning guide (screen only)');self.guide.setChecked(self.db.get('show_guides',True));self.guide.toggled.connect(self.update_guide);self.before=QCheckBox('Original background');self.before.toggled.connect(self.schedule_preview)
        preview_actions=QHBoxLayout();preview_actions.addWidget(QLabel('Quantity'))
        self.quantity=QSpinBox();self.quantity.setRange(1,10000);self.quantity.setValue(4);self.quantity.setMaximumWidth(100);self.quantity.valueChanged.connect(self.controls_changed);preview_actions.addWidget(self.quantity)
        self.quick_quantities=[]
        for n in (2,4,6,8):self.quick_quantities.append(self.button(str(n),lambda checked=False,v=n:self.quantity.setValue(v),preview_actions))
        from app.ui.icons import icon
        self.background_swatches=[]
        for name,color in [('Sky blue','#ADD8E6'),('White','#FFFFFF'),('Blue','#0078D4')]:
            swatch=QToolButton();swatch.setFixedSize(28,28);swatch.setCheckable(True);swatch.setAccessibleName('Background color: '+name);swatch.setToolTip('Background color');swatch.setStyleSheet(f'QToolButton {{background:{color};border:2px solid #7187a8;border-radius:4px;}} QToolButton:checked {{border:3px solid #24d5ef;}}');swatch.clicked.connect(lambda checked=False,c=color:self.set_color('background',c));preview_actions.addWidget(swatch);self.background_swatches.append((swatch,color))
        self.background_color=QToolButton();self.background_color.setText('…');self.background_color.setToolTip('Background color · More colors');self.background_color.setAccessibleName('More background colors');self.background_color.clicked.connect(lambda:self.pick_color('background'));preview_actions.addWidget(self.background_color)
        self.auto_soften=QPushButton('Auto soften');self.auto_soften.setCheckable(True);self.auto_soften.setToolTip('Natural face/skin smoothing. Click again to remove it. Original pixels stay unchanged.');self.auto_soften.clicked.connect(self.toggle_softener);preview_actions.addWidget(self.auto_soften)
        self.auto_fix=QPushButton('Auto Fix');self.auto_fix.setToolTip('Analyze the original subject and set color, tones, noise reduction, sharpening and skin softness. Undo restores your previous settings.');self.auto_fix.clicked.connect(self.auto_fix_portrait);preview_actions.addWidget(self.auto_fix)
        preview_actions.addStretch();self.top_preview=self.button('Preview PDF',self.show_print,self.editor_actions,True);outer.addLayout(preview_actions)
        options=QHBoxLayout();options.addWidget(self.guide);options.addWidget(self.before);options.addStretch();outer.addLayout(options)
        body=QHBoxLayout();outer.addLayout(body,1)
        left=QVBoxLayout();left.setSpacing(6);toolbar=QHBoxLayout();self.tool_group=QButtonGroup(self);self.tool_buttons={}
        for text,tool in [('Move / transform (V)','move'),('Erase (E)','erase'),('Restore (R)','restore')]:
            b=self.button('',lambda checked=False,t=tool:self.canvas.set_tool(t),toolbar);b.setIcon(icon(tool));b.setToolTip(text);b.setAccessibleName(text);b.setFixedSize(30,28);b.setCheckable(True);self.tool_group.addButton(b);self.tool_buttons[tool]=b
            if tool=='move':b.setChecked(True)
        self.brush_size=QSpinBox();self.brush_size.setMaximumWidth(80);self.brush_size.setRange(4,150);self.brush_size.setValue(24);self.brush_size.valueChanged.connect(lambda v:setattr(self.canvas,'brush_size',v));self.brush_caption=QLabel('Brush');toolbar.addWidget(self.brush_caption);toolbar.addWidget(self.brush_size);left.addLayout(toolbar)
        self.canvas=TransformCanvas();self.canvas.setMinimumSize(160,60);self.canvas.moved.connect(self.move_subject);self.canvas.zoomed.connect(self.zoom_subject);self.canvas.transformed.connect(self.commit_transform);self.canvas.layer_selected.connect(self.canvas_selection);self.canvas.painted.connect(self.commit_paint);self.canvas.tool_changed.connect(lambda tool:[b.setChecked(key==tool) for key,b in self.tool_buttons.items()]);self.canvas.brush_changed.connect(self.brush_size.setValue);left.addWidget(self.canvas,1)
        shapes=QHBoxLayout();self.shape_caption=QLabel('Select shape');shapes.addWidget(self.shape_caption)
        self.shape_picker=QComboBox()
        for label,key in [('Rectangle','rectangle'),('Square','square'),('Ellipse','ellipse'),('Circle','circle'),('Freehand','lasso'),('Polygon','polygon')]:self.shape_picker.addItem(label,key)
        def select_shape(index):
            key=self.shape_picker.itemData(index);self.canvas.set_tool({'square':'rectangle','circle':'ellipse'}.get(key,key));self.canvas.shape_constraint=key in ('square','circle');self.canvas.selection_mode='new';self.canvas.setFocus()
        self.shape_picker.activated.connect(select_shape);shapes.addWidget(self.shape_picker)
        for title,name,fn in [('Delete selected','delete',lambda:self.canvas.edit_selection()),('Deselect','deselect',lambda:self.canvas.modify_selection('deselect'))]:
            button=self.button('',fn,shapes);button.setIcon(icon(name));button.setFixedSize(30,28);button.setToolTip(title);button.setAccessibleName(title)
        toolbar.addLayout(shapes);toolbar.addStretch();self.shape_picker.setMaximumWidth(110)
        self.canvas.setToolTip('Drag a selection; Shift: square/circle; Ctrl+Shift: add. Delete: erase. Ctrl+wheel: zoom; Space+drag: pan; arrows: nudge.')
        from app.ui.preview_workspace import FloatingFit,FloatingPanelHost
        self.canvas_fit=FloatingFit(self.canvas)
        self.crop_hint=QLabel('Import a photograph to begin.');self.crop_hint.hide();canvas_area=QWidget();left.setContentsMargins(0,0,0,0);canvas_area.setLayout(left)
        panel=QWidget();panel_layout=QVBoxLayout(panel);panel_layout.setContentsMargins(0,0,0,0);tabs=QTabWidget();self.editor_tabs=tabs;panel_layout.addWidget(tabs,1)
        def tab(title):
            content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(10,8,10,12);layout.setSpacing(9);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setWidget(content);tabs.addTab(scroll,title);return layout
        tools=tab('Transform');self.section(tools,'CANVAS & SELECTED LAYER')
        self.profile_picker=QComboBox();self.profile_picker.setEditable(True);self.profile_picker.setInsertPolicy(QComboBox.NoInsert);self.profile_picker.setToolTip('Search profiles; select and Apply to preserve your existing layers.');tools.addWidget(self.profile_picker)
        self.apply_profile_button=self.button('Apply selected profile',self.apply_selected_profile,tools)
        sizes=QHBoxLayout();self.width=self.spin(5,1000,42);self.height=self.spin(5,1000,52);self.width.setSuffix(' mm');self.height.setSuffix(' mm');sizes.addWidget(self.width,1);sizes.addWidget(QLabel('×'));sizes.addWidget(self.height,1);self.button('↔',self.swap,sizes).setFixedWidth(35);tools.addLayout(sizes)
        for control in (self.width,self.height):control.setMaximumWidth(110)
        sizes.setSpacing(2)
        self.pair(tools,'Zoom',self.make_control('scale',.05,8,1,.05));self.pair(tools,'Horizontal',self.make_control('x',-3,4,.5,.02));self.pair(tools,'Vertical',self.make_control('y',-3,4,.5,.02));self.pair(tools,'Rotate',self.make_control('rotation',-180,180,0,1))
        crop_buttons=QHBoxLayout();self.button('Auto frame',self.auto_position,crop_buttons);self.button('Fit photo',lambda:self.fit_photo('fit'),crop_buttons);self.button('Fill canvas',lambda:self.fit_photo('fill'),crop_buttons);tools.addLayout(crop_buttons)
        row2=QHBoxLayout();self.button('Flip H',lambda:self.flip('flip_h'),row2);self.button('Flip V',lambda:self.flip('flip_v'),row2);self.button('Reset',self.reset_crop,row2);tools.addLayout(row2)
        row2=QHBoxLayout();self.button('Undo',self.undo_edit,row2);self.button('Redo',self.redo_edit,row2);tools.addLayout(row2)
        self.layer_visible=QCheckBox('Visible');self.layer_visible.setChecked(True);self.layer_visible.toggled.connect(self.controls_changed);self.layer_locked=QCheckBox('Lock layer');self.layer_locked.toggled.connect(self.controls_changed);row2=QHBoxLayout();row2.addWidget(self.layer_visible);row2.addWidget(self.layer_locked);tools.addLayout(row2)
        row2=QHBoxLayout();self.button('Bring forward',lambda:self.layer_order(1),row2);self.button('Send back',lambda:self.layer_order(-1),row2);tools.addLayout(row2)
        row2=QHBoxLayout();self.button('Align bottoms',lambda:self.align('safe_bottom'),row2);self.button('Match head sizes',lambda:self.align('match'),row2);tools.addLayout(row2)
        row2=QHBoxLayout();self.button('Align top',lambda:self.align('safe_top'),row2);self.button('Center H',lambda:self.align('center'),row2);self.button('Center V',lambda:self.align('vertical_center'),row2);tools.addLayout(row2)
        from app.ui.composition_controls import CompositionControls
        self.composition_controls=CompositionControls(self.db);self.composition_controls.apply_requested.connect(self.apply_composition);self.composition_controls.guides_changed.connect(lambda value:setattr(self.canvas,'safe_area_visible',value) or self.canvas.viewport().update());tools.addWidget(self.composition_controls);tools.addStretch()
        tools=tab('Finish');self.section(tools,'BACKGROUND & EDGE REFINEMENT')
        self.remove_button=self.button('Apply crop & remove background',self.remove_backgrounds,tools,True)
        self.background_status=QLabel('Background has not been removed.');self.background_status.setWordWrap(True);tools.addWidget(self.background_status)
        self.pair(tools,'Contract / expand edge',self.make_control('erosion',-8,8,0,1));self.pair(tools,'Edge softness',self.make_control('feather',0,8,0,.25))
        self.pair(tools,'Reduce edge halo',self.make_control('defringe',0,1,0,.05))
        tools.addStretch()
        tools=tab('Print')
        self.border=QCheckBox('Add border inside photo');self.border.setChecked(True);self.border.toggled.connect(self.controls_changed);tools.addWidget(self.border)
        self.border_mm=self.spin(0,5,.2,.05);self.border_mm.setSuffix(' mm');self.border_color=self.button('Border color · #808080',lambda:self.pick_color('border_color'),tools)
        self.section(tools,'PRINT SETTINGS')
        self.quantity_label=QLabel('Current quantity: 4');tools.addWidget(self.quantity_label)
        self.print_options=PrintOptions();self.paper=self.print_options.paper;self.print_options.changed.connect(self.print_options_changed);tools.addWidget(self.print_options)
        from app.services.print_geometry import ROTATIONS
        self.sheet_rotation=QComboBox()
        for key,title in ROTATIONS.items():self.sheet_rotation.addItem(title,key)
        self.sheet_rotation.activated.connect(self.change_sheet_rotation);self.pair(tools,'Sheet rotation',self.sheet_rotation)
        self.capacity=QLabel();self.capacity.setWordWrap(True);tools.addWidget(self.capacity)
        tools.addStretch()
        from app.ui.workflow_settings import WorkflowSettings
        self.photo_settings=WorkflowSettings(page,'Portrait / Joint');self.photo_settings.add_widget(panel);outer.removeItem(options);self.photo_settings.add_layout(options)
        self.photo_settings_button=self.button('',self.photo_settings.open_settings,self.editor_actions);self.photo_settings_button.setIcon(icon('settings'));self.photo_settings_button.setToolTip('Photo settings');self.photo_settings_button.setAccessibleName('Photo settings');self.photo_settings_button.setFixedWidth(34)
        self.floating_tabs=QTabWidget();self.floating_tabs.setMinimumSize(0,0)
        processing=QWidget();processing_form=QVBoxLayout(processing);processing_form.setContentsMargins(8,4,8,6);processing_form.setSpacing(5)
        processing_scroll=QScrollArea();processing_scroll.setWidgetResizable(True);processing_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);processing_scroll.setWidget(processing);self.floating_tabs.addTab(processing_scroll,'Image Processing')
        self.subject.setMinimumContentsLength(8);self.subject.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);processing_form.addWidget(self.subject)
        for label,key,low,high,value in [('Luminance noise','denoise',0,1,0),('Color noise','color_denoise',0,1,0),('Brightness','brightness',.4,1.8,1),('Contrast','contrast',.4,1.8,1),('Color','saturation',0,2,1),('Shadows','shadows',-1,1,0),('Warmth','temperature',-1,1,0),('Tint','tint',-1,1,0),('Sharpness','sharpness',0,3,1),('Skin soften','skin_soften',0,1,0)]:
            control=self.make_control(key,low,high,value,.05);control.setFixedWidth(100);self.pair(processing_form,label,control)
            control.setToolTip({'denoise':'Reduce grain in luminance while retaining edges.','color_denoise':'Reduce colored speckles separately from brightness detail.','skin_soften':'Smooth detected face/skin texture while protecting facial features. Zero removes softening.','tint':'Green (negative) to magenta (positive).','sharpness':'Thresholded sharpening above 1; below 1 softens the whole layer.'}.get(key,label))
        self.button('Reset processing',self.reset_adjustments,processing_form);processing_form.addStretch()
        basic=QWidget();basic_layout=QVBoxLayout(basic);basic_layout.setContentsMargins(6,4,6,6)
        for widget in (self.profile_picker,self.apply_profile_button):basic_layout.addWidget(widget)
        for layout in (sizes,crop_buttons):
            previous=layout.parent()
            if previous is not None:previous.removeItem(layout)
            basic_layout.addLayout(layout)
        for button in [crop_buttons.itemAt(i).widget() for i in range(crop_buttons.count())]:
            if button:button.setMinimumWidth(0)
        self.pair(basic_layout,'Border width',self.border_mm);basic_layout.addWidget(self.border_color);basic_layout.addWidget(self.border);basic_layout.addStretch()
        basic_scroll=QScrollArea();basic_scroll.setWidgetResizable(True);basic_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);basic_scroll.setWidget(basic);self.floating_tabs.addTab(basic_scroll,'Size')
        def advanced_tab(index):self.editor_tabs.setCurrentIndex(min(index,self.editor_tabs.count()-1));self.photo_settings.open_settings()
        self.editor_panel=AdaptivePanel(self.floating_tabs,self.db,'editor','Photo controls',default_width=280,minimum_width=160)
        self.editor_splitter=FloatingPanelHost(canvas_area,self.editor_panel);body.addWidget(self.editor_splitter)
        return page
    def make_control(self,name,*args):
        control=self.spin(*args);setattr(self,name,control);return control
    def print_page(self):
        page=QWidget();layout=QVBoxLayout(page);self.title('Your print sheet',layout,'Exact photo dimensions. Choose a layout and white separation without resizing your photos.')
        row=QHBoxLayout();self.button('← Back to photo',lambda:self.stack.setCurrentIndex(1),row);self.pages=QComboBox();self.pages.currentIndexChanged.connect(self.render_sheet);row.addWidget(self.pages);row.addStretch();self.button('Print…',lambda:self.hardware.print_job(self.job),row);self.button('Print to PDF',self.print_pdf,row,True);layout.addLayout(row)
        body=QHBoxLayout();self.sheet=PrintCanvas();self.sheet.changed.connect(self.sheet_moved)
        panel=QWidget();side=QVBoxLayout(panel);self.sheet_quantity=QSpinBox();self.sheet_quantity.setRange(1,10000);self.sheet_quantity.valueChanged.connect(lambda value:self.quantity.setValue(value));self.pair(side,'Current copies',self.sheet_quantity)
        row=QHBoxLayout();self.button('− 2 copies',lambda:self.change_quantity(-2),row);self.button('+ 2 copies',lambda:self.change_quantity(2),row);side.addLayout(row)
        self.sheet_options=PrintOptions();self.sheet_options.changed.connect(lambda:self.print_options_changed(source=self.sheet_options));side.addWidget(self.sheet_options);self.sheet_capacity=QLabel();self.sheet_capacity.setWordWrap(True);side.addWidget(self.sheet_capacity);self.button('Reset automatic layout',self.reset_layout,side);side.addStretch();self.sheet_panel=AdaptivePanel(panel,self.db,'sheet','Sheet controls',default_width=330);body.addWidget(splitter(self.sheet,self.sheet_panel));layout.addLayout(body,1)
        layout.addWidget(QLabel('Print at Actual Size / 100%. Dashed margins and positioning guides are screen-only.'));return page

    def apply_theme(self):
        from app.ui.theme import apply_theme
        apply_theme(self)
        if hasattr(self,'editor_splitter'):self.editor_splitter.refresh_theme()
    def notify(self,text):self.status.setText(text);self.status.setToolTip(text)
    def run(self,fn,done,on_error=None):
        if self.busy:self.notify('Finishing the current step…');return
        self.busy=True;self.progress.show();self.stack.setEnabled(False);self.home_button.setEnabled(False)
        for dialog in self.findChildren(QDialog):dialog.setEnabled(False)
        worker=Worker(fn);self.workers.add(worker)
        def finish(value,failed=False):
            self.busy=False;self.workers.discard(worker);self.progress.hide();self.stack.setEnabled(True);self.home_button.setEnabled(True)
            for dialog in self.findChildren(QDialog):dialog.setEnabled(True)
            if failed:
                if on_error:on_error(value)
                self.notify('This step failed. Your original photographs are unchanged.');QMessageBox.warning(self,'Could not finish this step',value)
            else:
                try:done(value)
                except Exception as e:QMessageBox.warning(self,'Could not finish this step',str(e))
        worker.signals.done.connect(lambda v:finish(v));worker.signals.error.connect(lambda v:finish(v,True));self.pool.start(worker)
    def save_before_leave(self):
        if self.busy or self._save_prompt_active:return False
        if hasattr(self,'shell'):
            document=self.shell.current_document()
            if document and not document.before_leave():return False
        self.invalidate_autosave()
        if not self.dirty:return True
        # A modal dialog runs a nested event loop: invalidate BEFORE asking.
        self.timer.stop();self._save_prompt_active=True
        try:
            result=QMessageBox.question(self,'Save your photo?','Save this photo job before leaving?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
        finally:self._save_prompt_active=False
        if result==QMessageBox.Save:
            saved=self.save_active_job()
            if not saved:self.schedule_preview()
            return saved
        if result==QMessageBox.Discard:
            try:
                exists=self.db.conn.execute('SELECT 1 FROM jobs WHERE id=?',(self.job.id,)).fetchone()
                self.adopt_job(self.db.load_job(self.job.id) if exists else Job())
                self.sync_controls()
                return True
            except Exception as error:
                QMessageBox.warning(self,'Could not discard',str(error))
        self.arm_autosave();self.schedule_preview()
        return False

    def invalidate_autosave(self):
        self._save_generation+=1;self.autosave.stop()
        if self._autosave_callback is not None:
            self.autosave.timeout.disconnect(self._autosave_callback)
            self._autosave_callback=None

    def arm_autosave(self,delay=2200):
        self.invalidate_autosave()
        if self._save_prompt_active:return
        token=(self._save_generation,self.job,self.job.id)
        self._autosave_callback=lambda:self.auto_save(token)
        self.autosave.timeout.connect(self._autosave_callback);self.autosave.start(delay)

    def current_save_token(self,token):
        return (not self._save_prompt_active and token[0]==self._save_generation
                and token[1] is self.job and token[2]==self.job.id)

    def adopt_job(self,job):
        """Replace the active editor document; no previous callback may save it."""
        self.invalidate_autosave();self.timer.stop()
        self.job=job;self.photo=job.photos[0] if job.photos else None
        if self.photo:self.mode='portrait' if self.photo.kind=='Individual' else 'joint'
        self.undo.clear();self.redo.clear();self.dirty=False
        self.canvas.display(Image.new('RGB',(450,550),'#e6edf2'))
    def home(self):
        if not self.busy and self.save_before_leave():self.timer.stop();self.studio.refresh();self.stack.setCurrentIndex(0)
    def start_workflow(self,mode):
        if self.busy or not self.save_before_leave():return False
        self.invalidate_autosave()
        self.mode=mode;self.photo=Photo(name='Portrait print' if mode=='portrait' else 'Joint photo print',kind='Individual' if mode=='portrait' else 'Joint composition',width=42 if mode=='portrait' else 55,height=52 if mode=='portrait' else 45,background='#ADD8E6')
        self.job=Job(name=self.photo.name,photos=[self.photo]);self.job.print_settings.update(margin=10,gap_x=.2,gap_y=.2,layout='auto',enforce_margins=True,dpi=300,auto_rotate_joint=True)
        profile_name=self.db.get('default_profile' if mode=='portrait' else 'joint_profile','Studio Portrait 42 x 52 mm' if mode=='portrait' else 'Studio Joint Photo')
        profile=next((p for p in self.db.profiles() if p['name']==profile_name),None)
        if profile:
            try:apply_profile(self.photo,profile,self.job.print_settings)
            except ValueError as e:self.notify('Default profile needs correction: '+str(e))
        else:self.photo.profile='Custom dimensions'
        for key in ('background','quantity','border','border_color','border_mm'):setattr(self.photo,key,self.db.get(key,getattr(self.photo,key)))
        for key in ('width','height'):setattr(self.photo,key,self.db.get(mode+'_'+key,getattr(self.photo,key)))
        for key in ('margin','gap_x','gap_y','landscape','layout','rows','columns','dpi'):self.job.print_settings[key]=self.db.get(key,self.job.print_settings.get(key,2 if key in ('rows','columns') else False))
        self.undo.clear();self.redo.clear();self.dirty=False;self.sync_print_options();self.refresh_profiles()
        self.workflow_title.setText(self.photo.name);self.canvas.display(Image.new('RGB',(450,550) if mode=='portrait' else (550,450),'#e6edf2'));self.crop_hint.setText('Choose one library photo and match the face and shoulders to the guide.' if mode=='portrait' else 'Choose one existing couple photo or two separate portraits. A combined photograph stays in one group.')
        self.floating_tabs.setCurrentIndex(0);self.sync_controls();self.stack.setCurrentIndex(1)
        return True
    def layer(self):
        i=self.subject.currentIndex();return self.photo.layers[i] if self.photo and 0<=i<len(self.photo.layers) else None
    def checkpoint(self):
        if self.photo:
            self.undo.append(self.edit_snapshot());self.undo=self.undo[-50:];self.redo.clear();self.dirty=True
            if hasattr(self,'autosave'):self.arm_autosave()
    def edit_snapshot(self):
        return copy.deepcopy((self.photo,self.job.print_settings,self.job.placements,self.job.page_count))
    def restore_edit(self,snapshot):
        self.photo,self.job.print_settings,self.job.placements,self.job.page_count=copy.deepcopy(snapshot)
        self.job.photos=[self.photo];self.dirty=True;self.sync_controls();self.arm_autosave()
    def refresh_profiles(self):
        if not hasattr(self,'profile_picker'):return
        current=self.photo.profile if self.photo else ''
        self.profile_picker.clear()
        for raw in self.db.profiles():
            p=normalize_profile(raw,validate=False)
            if p['kind']==('Individual' if self.mode=='portrait' else 'Joint'):self.profile_picker.addItem(p['name'])
        index=self.profile_picker.findText(current)
        self.profile_picker.setCurrentIndex(index)
        if index<0:self.profile_picker.setEditText('')
    def apply_selected_profile(self):
        if not self.photo or self.busy:return
        p=next((p for p in self.db.profiles() if p['name']==self.profile_picker.currentText()),None)
        if not p:self.notify('Select a saved profile from the list.');return
        try:p=normalize_profile(p)
        except ValueError as e:self.notify('Correct this profile in Photo Profiles: '+str(e));return
        self.checkpoint();apply_profile(self.photo,p,self.job.print_settings);self.job.placements=[];self.sync_controls();self.notify('Profile applied. Your layers, background masks and edits were kept.')
        usage=self.db.get('recipe_usage',{});usage[p['recipe_id']]=usage.get(p['recipe_id'],0)+1;self.db.set('recipe_usage',usage)
    def profiles_dialog(self):
        if self.busy:return
        dialog=QDialog(self);dialog.setWindowTitle('Photo profiles');layout=QVBoxLayout(dialog);layout.addWidget(Profiles(self.db,self.refresh_profiles));dialog.resize(900,650);dialog.exec()
    def sync_controls(self,*_,redraw=True):
        if not self.photo:return
        self.syncing=True;p=self.photo;self.composition_controls.load(p.composition)
        self.workflow_title.setText('Portrait Maker' if self.mode=='portrait' else 'Joint Photo Maker')
        self.sheet_rotation.setCurrentIndex(max(0,self.sheet_rotation.findData(p.print_rotation)))
        self.width.setValue(p.width);self.height.setValue(p.height);self.quantity.setValue(p.quantity);self.border.setChecked(p.border);self.border_mm.setValue(p.border_mm)
        labels=[]
        for i,layer in enumerate(p.layers):
            name=Path(layer.label).name if layer.label and Path(layer.label).is_absolute() else layer.label
            labels.append(('Combined group' if p.kind=='Combined joint' else f'Person {i+1}')+(' · '+name if name else ''))
        if [self.subject.itemText(i) for i in range(self.subject.count())]!=labels:
            previous=self.subject.currentIndex();self.subject.blockSignals(True);self.subject.clear();self.subject.addItems(labels);self.subject.setCurrentIndex(max(0,min(previous,len(labels)-1)));self.subject.blockSignals(False)
        l=self.layer()
        for key in ('scale','x','y','rotation','erosion','feather','defringe','brightness','contrast','saturation','sharpness','denoise','shadows','temperature','skin_soften','color_denoise','tint'):
            getattr(self,key).setValue(getattr(l,key) if l else (1 if key in ('scale','brightness','contrast','saturation','sharpness') else .5 if key in ('x','y') else 0))
        self.layer_visible.setChecked(l.visible if l else True);self.layer_locked.setChecked(l.locked if l else False)
        for key in ('scale','x','y','rotation','erosion','feather','defringe','brightness','contrast','saturation','sharpness','denoise','shadows','temperature','skin_soften','color_denoise','tint'):getattr(self,key).setEnabled(bool(l) and not l.locked)
        self.before.blockSignals(True);self.before.setChecked(False);self.before.blockSignals(False)
        count=sum(bool(l.mask) for l in p.layers)
        self.background_status.setText('Background removed. Choose a color below.' if p.layers and count==len(p.layers) else 'Background has not been removed.' if count==0 else f'{count} backgrounds removed.')
        self.remove_button.setText('Remove background again' if p.layers and count==len(p.layers) else 'Apply crop & remove background')
        self.border_color.setText('Border color · '+p.border_color)
        self.background_color.setToolTip('Background color · More colors · '+p.background)
        for swatch,color in self.background_swatches:swatch.setChecked(color.lower()==p.background.lower())
        active=[layer for layer in p.layers if layer.visible and not layer.locked]
        self.auto_soften.setChecked(bool(active) and all(layer.skin_soften>0 for layer in active));self.auto_soften.setEnabled(bool(active))
        self.auto_fix.setEnabled(bool(active))
        self.syncing=False;self.sync_print_options();self.update_capacity();self.update_guide()
        if redraw:self.schedule_preview()
    def controls_changed(self,*_):
        if self.syncing or not self.photo:return
        self.checkpoint();p=self.photo;old_size=(p.width,p.height);old_quantity=p.quantity;p.width=self.width.value();p.height=self.height.value();p.quantity=self.quantity.value();p.border=self.border.isChecked();p.border_mm=self.border_mm.value()
        l=self.layer()
        if l:
            if l.group and not l.locked:
                from app.services.layer_groups import transform_group
                transform_group(p,self.subject.currentIndex(),self.x.value(),self.y.value(),self.scale.value(),self.rotation.value())
            for key in ('scale','x','y','rotation','erosion','feather','defringe','brightness','contrast','saturation','sharpness','denoise','shadows','temperature','skin_soften','color_denoise','tint'):setattr(l,key,round(getattr(self,key).value()) if key=='erosion' else getattr(self,key).value())
            l.visible=self.layer_visible.isChecked();l.locked=self.layer_locked.isChecked()
        if old_size!=(p.width,p.height):self.job.placements=[]
        elif old_quantity!=p.quantity:
            try:resize_copies(self.job)
            except ValueError as e:self.notify(str(e));self.job.placements=[]
        self.sync_print_options();self.update_capacity();self.schedule_preview()
    def print_options_changed(self,*_,source=None):
        if not self.photo or self.syncing:return
        self.checkpoint();self.job.print_settings.update((source or self.print_options).value());self.job.print_settings['auto_orientation']=False;self.job.placements=[];self.sync_print_options();self.update_capacity();self.schedule_preview()
    def sync_print_options(self):
        for options in (self.print_options,self.sheet_options):options.load(self.job.print_settings)
        if self.photo:
            self.sheet_quantity.blockSignals(True);self.sheet_quantity.setValue(self.photo.quantity);self.sheet_quantity.blockSignals(False);self.quantity_label.setText(f'Current quantity: {self.photo.quantity}')
    def change_quantity(self,delta):self.quantity.setValue(max(1,min(10000,self.quantity.value()+delta)))
    def reset_layout(self):
        if self.photo and not self.busy:self.checkpoint();self.job.placements=[];self.show_print()
    def update_capacity(self):
        if not self.photo:return
        try:
            columns,rows=layout_capacity(self.photo,self.job.print_settings);pages=self.job.page_count if self.job.placements else math.ceil(self.photo.quantity/(columns*rows));text=f'{columns} photos per row × {rows} rows; up to {columns*rows} per page. {self.photo.quantity} copies, {pages} page(s). Photo size stays {self.photo.width:g} × {self.photo.height:g} mm.'
        except ValueError as e:text=str(e)
        self.capacity.setText(text);self.sheet_capacity.setText(text)
    def update_guide(self,*_):self.canvas.set_guides((1 if self.mode=='portrait' else 2) if self.guide.isChecked() else 0)
    def schedule_preview(self,*_):self.timer.start()
    def render_preview(self):
        if self.stack.currentIndex()==2:
            if self.busy:self.timer.start(200);return
            self.show_print();return
        if self.stack.currentIndex()!=1:return
        if not self.photo or not self.photo.layers:return
        if self.busy:self.timer.start(200);return
        photo=copy.deepcopy(self.photo);before=self.before.isChecked();index=self.subject.currentIndex()
        mask_only=hasattr(self,'editor_tools') and self.editor_tools.mask_only.isChecked()
        def render():
            images=[prepare_layer(l,before) for l in photo.layers]
            for image in images:image.thumbnail((1400,1400),Image.Resampling.LANCZOS)
            if mask_only and 0<=index<len(images):images[index]=images[index].getchannel('A').convert('RGBA')
            return images
        self.run(render,lambda images:self.canvas.set_layers(photo,images,index))
    def move_subject(self,dx,dy):
        l=self.layer()
        if l and not l.locked:self.commit_transform(self.subject.currentIndex(),l.x+dx,l.y+dy,l.scale,l.rotation)
    def zoom_subject(self,factor):
        l=self.layer()
        if l and not l.locked:self.commit_transform(self.subject.currentIndex(),l.x,l.y,min(8,max(.05,l.scale*factor)),l.rotation)
    def swap(self):
        if self.photo:self.checkpoint();self.photo.swap();self.job.placements=[];self.sync_controls()
    def reset_crop(self):
        l=self.layer()
        if l and not l.locked:
            self.checkpoint();count=len(self.photo.layers);l.x=.5 if count==1 else (self.subject.currentIndex()+.5)/count;l.y=.5;l.scale=1 if count==1 else .68;l.rotation=0;l.flip_h=l.flip_v=False;self.sync_controls()
    def undo_edit(self):
        if self.busy:return
        if self.stack.currentIndex()==3:self.cropper.undo_crop();return
        if self.stack.currentIndex() not in (1,2):return
        if self.undo and not self.busy:self.redo.append(self.edit_snapshot());self.restore_edit(self.undo.pop())
    def redo_edit(self):
        if self.busy:return
        if self.stack.currentIndex()==3:self.cropper.redo_crop();return
        if self.stack.currentIndex() not in (1,2):return
        if self.redo and not self.busy:self.undo.append(self.edit_snapshot());self.restore_edit(self.redo.pop())
    def canvas_selection(self,index):
        self.subject.blockSignals(True);self.subject.setCurrentIndex(index);self.subject.blockSignals(False);self.sync_controls(redraw=False)
    def commit_transform(self,index,x,y,scale,rotation):
        if not self.photo or not 0<=index<len(self.photo.layers):return
        layer=self.photo.layers[index]
        if layer.locked:return
        from app.services.layer_groups import transform_group
        self.checkpoint();transform_group(self.photo,index,x,y,min(8,max(.05,scale)),((rotation+180)%360)-180);self.sync_controls()
    def commit_paint(self,index,stroke):
        if not self.busy and self.photo and 0<=index<len(self.photo.layers) and not self.photo.layers[index].locked and self.photo.layers[index].visible:
            self.checkpoint();self.photo.layers[index].mask_strokes.append(stroke);self.sync_controls()
    def change_sheet_rotation(self,*_):
        if self.photo and not self.busy:
            self.checkpoint();self.photo.print_rotation=self.sheet_rotation.currentData();self.job.placements=[];self.sync_controls()
    def flip(self,key):
        layer=self.layer()
        if layer and not layer.locked:self.checkpoint();setattr(layer,key,not getattr(layer,key));self.sync_controls()
    def layer_order(self,delta):
        i=self.subject.currentIndex();j=i+delta
        if self.photo and 0<=j<len(self.photo.layers):
            self.checkpoint();self.photo.layers[i],self.photo.layers[j]=self.photo.layers[j],self.photo.layers[i];self.subject.blockSignals(True);self.subject.clear();self.subject.blockSignals(False);self.sync_controls();self.subject.setCurrentIndex(j)
    def reset_adjustments(self):
        layer=self.layer()
        if layer and not layer.locked:
            self.checkpoint()
            for key in ('brightness','contrast','saturation','sharpness'):setattr(layer,key,1.)
            from app.models.domain import PROCESSING_LIMITS
            for key in PROCESSING_LIMITS:setattr(layer,key,0.)
            self.sync_controls()
    def toggle_softener(self,enabled):
        if self.busy or not self.photo:return
        self.checkpoint()
        for layer in self.photo.layers:
            if layer.visible and not layer.locked:layer.skin_soften=.6 if enabled else 0.
        self.sync_controls()
        if enabled:self.notify('Face/skin softening enabled. No detected face means no skin change; use Auto Fix for a detection summary.')
    def auto_fix_portrait(self):
        if self.busy or not self.photo:return
        from app.services.imaging import load_image
        from app.services.portrait_processing import auto_adjustments
        layers=[(index,copy.deepcopy(layer)) for index,layer in enumerate(self.photo.layers) if layer.visible and not layer.locked]
        if not layers:return
        document=self.photo
        def analyze():return [(index,*auto_adjustments(load_image(layer.mask or layer.source,2000))) for index,layer in layers]
        def done(results):
            if self.photo is not document:return
            self.checkpoint()
            for index,values,found in results:
                for key,value in values.items():setattr(document.layers[index],key,value)
            self.sync_controls()
            missing=sum(not found for _,_,found in results)
            self.notify('Auto Fix applied. Undo restores the previous settings.'+ (f' No face found in {missing} layer(s); skin softening was left off there.' if missing else ' Face/skin softening included.'))
        self.run(analyze,done)
    def fit_photo(self,mode='auto'):
        if mode=='auto':mode='balanced'
        if self.busy or not self.photo or not self.photo.layers:return
        photo=copy.deepcopy(self.photo)
        def done(result):self.checkpoint();self.photo=result;self.job.photos=[result];self.sync_controls()
        self.run(lambda:frame_photo(photo,mode),done)
    def align(self,action):
        if self.busy or not self.photo:return
        photo=copy.deepcopy(self.photo)
        def done(result):self.checkpoint();self.photo=result;self.job.photos=[result];self.sync_controls()
        self.run(lambda:align_layers(photo,action),done)
    def auto_save(self,token):
        if not self.current_save_token(token) or not self.dirty or not self.photo or not self.photo.layers:return
        if self.busy:self.arm_autosave(500);return
        try:
            self.photo.validate();self.db.save_job(self.job);self.studio.link_job(self.job)
            self.dirty=False;self.invalidate_autosave()
        except Exception as e:self.notify('Could not auto-save: '+str(e))
    def set_color(self,field,color):
        if self.photo:self.checkpoint();setattr(self.photo,field,color);self.sync_controls()
    def pick_color(self,field):
        if not self.photo:return
        color=QColorDialog.getColor(QColor(getattr(self.photo,field)),self)
        if color.isValid():self.set_color(field,color.name())

    def import_photos(self,checked=False,paths=None):
        if self.busy:return
        if self.photo is None:self.start_workflow('portrait')
        if self.stack.currentIndex()==0:self.stack.setCurrentIndex(1)
        if paths is None:paths,_=QFileDialog.getOpenFileNames(self,'Choose one portrait' if self.mode=='portrait' else 'Choose two people',dialog_folder(self.db,'input',self.notify),'Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)')
        if not paths:return
        required=1 if self.mode=='portrait' else 2
        if len(paths)!=required:QMessageBox.information(self,'Choose photographs',f'Please choose {required} photograph'+('s.' if required>1 else '.'));return
        width,height=self.photo.width,self.photo.height
        self.notify('Importing and detecting faces for the initial crop…')
        def process():
            layers=[];notes=[]
            for i,path in enumerate(paths):
                source,size,thumb=import_info(path);l=Layer(source)
                try:
                    l=face_position(l,width,height)
                    if required==2:l.x+=[-.23,.23][i]
                except ValueError:
                    l.x=.5 if required==1 else [.27,.73][i];l.scale=1 if required==1 else .68;notes.append(f'Person {i+1}: no face detected; use the guide to adjust manually.')
                layers.append(l)
            return layers,notes
        def done(result):
            self.checkpoint();self.photo.layers=result[0];self.job.placements=[];self.subject.clear();self.sync_controls();self.stack.setCurrentIndex(1)
            self.crop_hint.setText(' '.join(result[1]) or 'Auto-crop ready. Drag to move, scroll to zoom. Match eyes, head and shoulders to the guide.');self.notify('Adjust the crop, then click Apply crop & remove background.')
        self.run(process,done)
    def open_cropper(self,checked=False,load_source=True):
        if self.busy or not self.save_before_leave():return False
        self.timer.stop();self.stack.setCurrentIndex(3);self.cropper.refresh_tray();self.notify('Cropper: prepare separate photos, then choose them in Portrait or Joint print.')
        if load_source and self.cropper.current_image is None and self.cropper.source_paths:self.cropper.select_source(self.cropper.sources.currentIndex())
        return True
    def import_to_cropper(self,checked=False,paths=None):
        if self.busy:return
        if self.open_cropper(load_source=False):self.cropper.import_sources(paths=paths)
    def choose_prepared(self):
        if self.busy:return
        if not self.tray.items:self.open_cropper();self.notify('Your crop tray is empty. Import a source and keep one or more crops first.');return
        picker=PreparedPicker(self.tray,1 if self.mode=='portrait' else (1,2),self)
        if picker.exec():self.load_prepared(picker.chosen())
    def use_crops(self,mode,items):
        if self.start_workflow(mode):self.load_prepared(items)
    def load_prepared(self,items):
        if self.busy:return
        if len(items) not in ((1,) if self.mode=='portrait' else (1,2)):raise ValueError('Choose one portrait, or one combined/two separate joint photos.')
        required=len(items)
        width,height=self.photo.width,self.photo.height;model_dir=self.db.get('model_dir');quality=self.db.get('processing_quality','balanced');framing=self.db.get('automatic_framing','balanced');framing='balanced' if framing=='auto' else framing;photo_snapshot=copy.deepcopy(self.photo)
        photo_snapshot.provenance={'library_ids':[p.id for p in items]}
        try:model=find_background_model(model_dir)
        except ValueError as e:QMessageBox.warning(self,'Background model needed',str(e));return
        self.notify('Preparing selected crops: auto-positioning and removing their original backgrounds…')
        def process():
            layers=[];notes=[]
            for i,item in enumerate(items):
                path=self.tray.materialize(item,data_root()/'job_assets');l=Layer(path,label=item.display_name)
                l.mask=remove_background(path,str(model.parent),data_root()/'cache',quality=quality);layers.append(l)
            photo=photo_snapshot;photo.layers=layers;photo.kind='Combined joint' if self.mode=='joint' and required==1 else 'Joint composition' if self.mode=='joint' else 'Individual';frame_photo(photo,framing)
            return photo,notes
        def done(result):
            self.checkpoint();self.photo=result[0];self.job.photos=[self.photo];self.job.name='Joint '+ ' + '.join(f'{p.serial:06d}' for p in items) if self.mode=='joint' else f'Portrait {items[0].serial:06d}';self.job.placements=[];self.subject.blockSignals(True);self.subject.clear();self.subject.blockSignals(False);self.sync_controls();self.stack.setCurrentIndex(1)
            self.photo.name=('Joint ' if self.mode=='joint' else 'Portrait ')+ ' + '.join(f'#{p.serial:06d}' for p in items)
            self.crop_hint.setText(' '.join(result[1]) or 'Prepared crops loaded and backgrounds removed. Adjust each person against the guide if needed.');self.notify('Backgrounds removed from the separate crops. Sky blue is selected by default.')
        self.run(process,done)
    def apply_composition(self,mode,settings):
        if not self.photo or self.busy:return
        snapshot=copy.deepcopy(self.photo);snapshot.composition=dict(settings,mode=mode)
        def done(result):self.checkpoint();self.photo=result;self.job.photos=[result];self.sync_controls()
        self.run(lambda:frame_photo(snapshot,mode),done)
    def auto_position(self):
        self.fit_photo('auto')
    def remove_backgrounds(self):
        if not self.photo or not self.photo.layers:self.notify('Import your photograph first.');return
        model_dir=self.db.get('model_dir');layers=list(self.photo.layers);quality=self.db.get('processing_quality','balanced')
        try:model=find_background_model(model_dir)
        except ValueError as e:QMessageBox.warning(self,'Background model needed',str(e));return
        self.notify('Removing background locally. Please wait…');self.background_status.setText('Removing background…')
        def process():return [remove_background(l.source,str(model.parent),data_root()/'cache',force=True,quality=quality) for l in layers]
        def done(paths):
            self.checkpoint()
            for l,path in zip(layers,paths):l.mask=path
            self.before.setChecked(False);self.sync_controls();self.notify('Background removed. Sky blue is selected; choose another color if needed.')
        self.run(process,done)

    def show_print(self):
        if not self.photo or not self.photo.layers:self.notify('Import a photograph first.');return
        if not any(layer.visible for layer in self.photo.layers):self.notify('Show at least one photo layer before printing.');return
        if self.busy:return
        try:
            self.photo.validate()
            if not self.job.placements:
                if self.job.print_settings.get('auto_orientation'):
                    from app.services.print_sessions import choose_orientation
                    self.job.print_settings,self.job.placements,self.job.page_count=choose_orientation(self.job.photos,self.job.print_settings)
                else:self.job.placements=auto_layout(self.job.photos,self.job.print_settings);self.job.page_count=max(r.page for r in self.job.placements)+1
            validate_layout(self.job)
        except Exception as e:QMessageBox.warning(self,'Check photo size',str(e));return
        current=max(0,self.pages.currentIndex());self.pages.blockSignals(True);self.pages.clear();self.pages.addItems([f'Page {i+1} of {self.job.page_count}' for i in range(self.job.page_count)]);self.pages.setCurrentIndex(min(current,self.job.page_count-1));self.pages.blockSignals(False);self.timer.stop();self.stack.setCurrentIndex(2);self.sync_print_options();self.update_capacity();self.render_sheet()
    def render_sheet(self,*_):
        if self.busy or not self.job.placements:return
        photo=copy.deepcopy(self.photo);page=max(0,self.pages.currentIndex())
        def render():return render_photo(photo,180)
        self.run(render,lambda im:self.sheet.display(self.job,page,{photo.id:im},vector_borders=True))
    def sheet_moved(self):self.dirty=True;self.arm_autosave();self.render_sheet()
    def print_pdf(self):
        if self.busy:return
        try:validate_layout(self.job)
        except Exception as e:QMessageBox.warning(self,'Check sheet',str(e));return
        filename=''.join(c if c not in '<>:"/\\|?*' else '-' for c in self.job.name)
        path,_=QFileDialog.getSaveFileName(self,'Print to PDF',dialog_output(self.db,filename+'.pdf',self.notify),'PDF (*.pdf)')
        if not path:return
        if Path(path).resolve() in self.protected_paths():QMessageBox.warning(self,'Original protected','Choose a different filename.');return
        from app.services.export_safety import check_export_target
        try:check_export_target(path,self.db.path.parent,self.db.conn,self.protected_paths())
        except ValueError as e:QMessageBox.warning(self,'Export location',str(e));return
        snapshot=copy.deepcopy(self.job)
        def checked(warnings):
            if warnings and QMessageBox.question(self,'Image resolution','\n'.join(warnings)+'\nContinue with this photo?')!=QMessageBox.Yes:return
            def done(result):
                self.save_job()
                with self.db.conn:self.db.conn.execute('INSERT INTO exports(path) VALUES(?)',(result,))
                self.notify('PDF ready. Print at Actual Size / 100%.');QDesktopServices.openUrl(QUrl.fromLocalFile(result))
            self.run(lambda:export_pdf(snapshot,path,dpi=int(snapshot.print_settings.get('dpi',300))),done)
        self.run(lambda:resolution_warnings(snapshot.photos[0]),checked)
    def save_job(self):
        if hasattr(self,'shell'):
            document=self.shell.current_document()
            if document:return document.save_session()
            if self.stack.currentWidget() is getattr(self.shell,'preferences',None):self.shell.preferences.save();return True
        if hasattr(self,'studio') and self.stack.currentWidget() is self.studio.multi:
            try:self.studio.multi.persist();self.notify('Print session saved on this PC.');return True
            except ValueError as e:self.notify(str(e));return False
        return self.save_active_job()

    def save_active_job(self):
        if self.busy or self._save_prompt_active or not self.photo or not self.photo.layers:return False
        self.invalidate_autosave()
        try:
            self.photo.validate();self.db.save_job(self.job);self.studio.link_job(self.job)
            self.dirty=False;self.notify('Job saved on this PC.');return True
        except Exception as e:
            if self.dirty:self.arm_autosave()
            QMessageBox.warning(self,'Could not save',str(e));return False
    def export_image(self):
        if self.busy or not self.photo or not self.photo.layers:return
        path,_=QFileDialog.getSaveFileName(self,'Export edited photograph',dialog_output(self.db,self.job.name+'.png',self.notify),'PNG (*.png);;JPEG (*.jpg)')
        if not path:return
        protected=self.protected_paths()
        if Path(path).resolve() in protected:QMessageBox.warning(self,'Original protected','Choose a new output filename.');return
        from app.services.export_safety import check_export_target
        try:check_export_target(path,self.db.path.parent,self.db.conn,protected)
        except ValueError as e:QMessageBox.warning(self,'Export location',str(e));return
        photo=copy.deepcopy(self.photo)
        dpi=int(self.job.print_settings.get('dpi',300))
        def write():return export_photo_image(photo,path,dpi)
        self.run(write,lambda result:self.notify('Edited photograph exported: '+result))
    def protected_paths(self):
        paths=[path for l in self.photo.layers for path in (l.source,l.mask) if path] if self.photo else []
        paths.extend(p.asset for p in self.tray.items if p.asset);paths.extend(self.cropper.source_paths)
        return {Path(p).resolve() for p in paths}
    @recoverable_record
    def open_jobs(self):
        if self.busy:return
        d=QDialog(self);d.setWindowTitle('Saved jobs');layout=QVBoxLayout(d);listing=QListWidget();rows=self.db.jobs();listing.addItems([name+' · '+date for id,name,date in rows]);layout.addWidget(listing);buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject);layout.addWidget(buttons);d.resize(650,450)
        if d.exec() and listing.currentRow()>=0 and self.save_before_leave():
            job=checked_document(self.db.load_job(rows[listing.currentRow()][0]))
            if not job.photos:return
            if len(job.photos)>1 or self.db.conn.execute('SELECT 1 FROM print_sessions WHERE job_id=?',(job.id,)).fetchone():self.studio.open_job(job.id);return
            self.adopt_job(job)
            self.workflow_title.setText('Portrait print' if self.mode=='portrait' else 'Joint photo print');self.refresh_profiles();self.subject.blockSignals(True);self.subject.clear();self.subject.blockSignals(False);self.sync_controls();self.stack.setCurrentIndex(1)
    def settings_dialog(self):
        if self.busy:return
        if self.dirty:self.save_job()
        references=tuple(path for l in self.photo.layers for path in (l.source,l.mask) if path) if self.photo else ()
        self.dialog=QDialog(self);self.dialog.setWindowTitle('Studio preferences');layout=QVBoxLayout(self.dialog);layout.addWidget(Settings(self.db,self.run,self.notify,self.apply_theme,self.refresh_profiles,self.restore_backup,references));self.dialog.resize(850,800);self.dialog.show()
    def restore_backup(self):
        if self.hardware.operation_active():self.notify('Wait for scanning or printing to finish before restoring data.');return
        if not self.save_before_leave():return
        if self.busy:return
        path,_=QFileDialog.getOpenFileName(self,'Verify studio backup',dialog_folder(self.db,'backups',self.notify),'Studio backup (*.zip)')
        if not path:return
        root=data_root()
        def ready(stage):
            answer=QMessageBox.question(self,'Restore verified backup','Checksums and databases are valid. Replace the current jobs, library and settings with this backup and restart? The entire current data folder will be retained beside the restored folder.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
            if answer!=QMessageBox.Yes:
                self.run(lambda:discard_restore(stage,root),lambda _:self.notify('Restore canceled. Current data is unchanged.'));return
            self.hardware.shutdown();self.timer.stop();self.invalidate_autosave();self.pool.waitForDone();self.shell.shutdown();self.tray.close();self.db.conn.close()
            try:previous=install_restore(stage,root)
            except Exception as e:
                self.db=Database();self.tray=CropTray(root=root/'library');self.cropper.tray=self.tray
                self.studio.rebind()
                self.shell.rebind()
                if hasattr(self,'dialog'):self.dialog.close()
                QMessageBox.warning(self,'Restore could not be installed',str(e)+'\nThe previous data folder was retained.');return
            executable=sys.executable;arguments=[] if getattr(sys,'frozen',False) else [str(Path(__file__).resolve().parents[2]/'main.py')]
            started=QProcess.startDetached(executable,arguments,str(Path(executable).parent) if getattr(sys,'frozen',False) else str(Path(__file__).resolve().parents[2]))
            if not started[0]:QMessageBox.information(self,'Restore complete','Data restored. Reopen the application manually. Previous data: '+previous)
            self._restore_closing=True
            if hasattr(self,'dialog'):self.dialog.close()
            self.close()
        self.run(lambda:prepare_restore(path,root),ready)
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
    def dropEvent(self,e):self.import_to_cropper(paths=[u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
    def closeEvent(self,e):
        if getattr(self,'_restore_closing',False):e.accept();return
        if self.hardware.operation_active():
            e.ignore();self.notify('A scan or print submission is active. Request scan cancellation or wait for the driver before closing. Completed scans remain saved.');return
        if self.busy:e.ignore();self.notify('Please wait for the current step to finish.');return
        if hasattr(self,'shell'):
            for document in (self.shell.copy,self.shell.nid):
                if not document.before_leave():e.ignore();return
        if not self.save_before_leave():e.ignore();return
        self.hardware.shutdown();self.timer.stop();self.invalidate_autosave();self.pool.waitForDone();self.shell.shutdown();self.tray.close();self.db.conn.close();e.accept()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'shell'):self.shell.resize(self.size().width())
