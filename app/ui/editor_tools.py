"""Additional tools operate on the existing editor, renderer and undo snapshots."""
import copy
import uuid
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QDoubleSpinBox,QCheckBox,QPushButton,QInputDialog,QComboBox


class EditorTools(QWidget):
    def __init__(self,w):
        from PySide6.QtWidgets import QFormLayout,QGridLayout
        from app.services.selections import TOOLS
        super().__init__();self.w=w;outer=QVBoxLayout(self);outer.setContentsMargins(10,8,10,12)
        w.canvas.selection_error.connect(w.notify)
        intro=QLabel('Choose a shape above the canvas, drag over the unwanted area, then press Delete. Shift makes a square or circle; Ctrl adds another area.');intro.setWordWrap(True);outer.addWidget(intro)
        more=QPushButton('More mask and layer controls');more.setCheckable(True);outer.addWidget(more)
        advanced=QWidget();advanced_layout=QVBoxLayout(advanced);advanced_layout.setContentsMargins(0,0,0,0);outer.addWidget(advanced);advanced.hide();more.toggled.connect(advanced.setVisible);self.advanced=advanced
        outer=advanced_layout
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);outer.addLayout(form)
        self.selection_tool=QComboBox();self.selection_tool.addItem('Move / transform','move')
        for key,title in TOOLS.items():self.selection_tool.addItem(title,key)
        self.selection_tool.addItem('Erase brush','erase');self.selection_tool.addItem('Restore brush','restore')
        restore_tip='Restore brush reveals original source pixels and alpha, including the old background. Restore Selection restores the starting processed mask instead.'
        self.selection_tool.setToolTip(restore_tip);w.tool_buttons['restore'].setToolTip(restore_tip)
        self.selection_tool.activated.connect(lambda _:w.canvas.set_tool(self.selection_tool.currentData()))
        w.canvas.tool_changed.connect(lambda key:self.selection_tool.setCurrentIndex(max(0,self.selection_tool.findData(key))))
        form.addRow('Tool',self.selection_tool)
        self.selection_mode=QComboBox()
        for mode in ('new','add','subtract','intersect'):self.selection_mode.addItem(mode.title(),mode)
        self.selection_mode.activated.connect(lambda _:setattr(w.canvas,'selection_mode',self.selection_mode.currentData()))
        form.addRow('Combine selection',self.selection_mode)
        self.hardness=QDoubleSpinBox();self.opacity=QDoubleSpinBox()
        for label,control,value,key in [('Hardness',self.hardness,.75,'brush_hardness'),('Opacity',self.opacity,1,'brush_opacity')]:
            control.setRange(0,1);control.setSingleStep(.05);control.setValue(value);setattr(w.canvas,key,value);control.valueChanged.connect(lambda value,key=key:setattr(w.canvas,key,value));form.addRow(label,control)
        self.brush_feather=QDoubleSpinBox();self.brush_feather.setRange(0,100);self.brush_feather.setSuffix(' preview px');self.brush_feather.valueChanged.connect(lambda value:setattr(w.canvas,'brush_feather',value));form.addRow('Brush feather',self.brush_feather)
        self.selection_radius=QDoubleSpinBox();self.selection_radius.setRange(.1,500);self.selection_radius.setValue(3);self.selection_radius.setSuffix(' source px');form.addRow('Refine radius',self.selection_radius)
        grid=QGridLayout();outer.addLayout(grid)
        actions=[('Select all',lambda:w.canvas.modify_selection('all')),('Deselect',lambda:w.canvas.modify_selection('deselect')),('Invert',lambda:w.canvas.modify_selection('invert')),('Erase selection',lambda:w.canvas.edit_selection()),('Restore selection',lambda:w.canvas.edit_selection(True))]
        actions += [(op.title(),lambda _,op=op:self.refine_selection(op)) for op in ('feather','expand','contract')]
        for i,(title,fn) in enumerate(actions):
            b=QPushButton(title);b.clicked.connect(fn);grid.addWidget(b,i//2,i%2)
            if title=='Restore selection':b.setToolTip('Restore starting mask visibility inside the selection. Use Restore brush only when you want original source visibility, which can reveal the old background.')
        self.mask_only=QCheckBox('Mask-only preview');self.mask_only.toggled.connect(w.schedule_preview);outer.addWidget(self.mask_only)
        hint=QLabel('M: rectangle · Shift+M: ellipse\nL: lasso · Shift+L: polygon · B: selection brush\nEnter ends polygon · Delete erases selection\nShift constrains · Ctrl adds · Alt subtracts.\nRestore brush can reveal the old background. Restore selection restores the starting mask.');hint.setWordWrap(True);hint.setObjectName('muted');outer.addWidget(hint)
        grid=QGridLayout();outer.addLayout(grid)
        for i,(title,fn) in enumerate([('Rename layer',self.rename),('Duplicate layer',self.duplicate),('Group visible',self.group),('Ungroup selected',self.ungroup),('Reset mask / tone',self.clear)]):
            b=QPushButton(title);b.clicked.connect(fn);grid.addWidget(b,i//2,i%2)
        form=QFormLayout();outer.addLayout(form);self.colors=QComboBox();self.colors.addItems(['Sky blue','White','Light gray','Dark gray','Red']);self.colors.activated.connect(self.preset);form.addRow('Background',self.colors)
        self.recent=QComboBox();self.recent.addItems(w.db.get('recent_colors',[]));self.recent.activated.connect(lambda index:self.background(self.recent.itemText(index)));form.addRow('Recent colors',self.recent)
        reset=QPushButton('Reset sky blue');reset.clicked.connect(lambda:self.background('#ADD8E6'));outer.addWidget(reset);outer.addStretch()
    def refine_selection(self,operation):
        layer=self.w.layer()
        if not layer:return
        from PIL import Image,ImageOps
        with Image.open(layer.source) as source:width=ImageOps.exif_transpose(source).width
        self.w.canvas.modify_selection(operation,self.selection_radius.value()/width)
    def background(self,color):
        self.w.set_color('background',color);values=[color]+[c for c in self.w.db.get('recent_colors',[]) if c!=color];self.w.db.set('recent_colors',values[:10]);self.recent.clear();self.recent.addItems(values[:10])
    def preset(self,index):self.background(['#ADD8E6','#FFFFFF','#D3D3D3','#444444','#E53935'][index])
    def refresh_layers(self,index):
        self.w.subject.blockSignals(True);self.w.subject.clear();self.w.subject.blockSignals(False);self.w.sync_controls();self.w.subject.setCurrentIndex(index)
    def rename(self):
        layer=self.w.layer()
        if not layer:return
        label,ok=QInputDialog.getText(self,'Rename layer','Layer name',text=layer.label)
        if ok and label.strip():self.w.checkpoint();layer.label=label.strip();self.refresh_layers(self.w.subject.currentIndex())
    def duplicate(self):
        layer=self.w.layer()
        if not layer:return
        self.w.checkpoint();p=copy.deepcopy(layer);p.label=(p.label or 'Layer')+' copy';p.group='';self.w.photo.layers.append(p);self.refresh_layers(len(self.w.photo.layers)-1)
    def group(self):
        if not self.w.photo:return
        self.w.checkpoint();id=uuid.uuid4().hex
        for layer in self.w.photo.layers:
            if layer.visible and not layer.locked:layer.group=id
        self.w.notify('Visible unlocked layers grouped. Move, rotate or scale a member to transform the group.');self.w.sync_controls()
    def ungroup(self):
        layer=self.w.layer()
        if layer and layer.group:
            group=layer.group;self.w.checkpoint()
            for member in self.w.photo.layers:
                if member.group==group:member.group=''
            self.w.sync_controls()
    def clear(self):
        layer=self.w.layer()
        if layer and not layer.locked:
            self.w.checkpoint();layer.mask_strokes=[];layer.erosion=0;layer.feather=0;layer.defringe=0
            for key in ('brightness','contrast','saturation','sharpness'):setattr(layer,key,1.)
            for key in ('denoise','shadows','temperature','skin_soften'):setattr(layer,key,0.)
            self.w.sync_controls()
