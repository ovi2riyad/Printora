"""Additional tools operate on the existing editor, renderer and undo snapshots."""
import copy
import uuid
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QDoubleSpinBox,QCheckBox,QPushButton,QInputDialog,QComboBox


class EditorTools(QWidget):
    def __init__(self,w):
        super().__init__();self.w=w;outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();self.hardness=QDoubleSpinBox();self.opacity=QDoubleSpinBox()
        for label,control,value,key in [('Hardness',self.hardness,.75,'brush_hardness'),('Opacity',self.opacity,1,'brush_opacity')]:
            control.setRange(0,1);control.setSingleStep(.05);control.setValue(value);setattr(w.canvas,key,value);control.valueChanged.connect(lambda value,key=key:setattr(w.canvas,key,value));row.addWidget(QLabel(label));row.addWidget(control)
        self.mask_only=QCheckBox('Mask-only preview');self.mask_only.toggled.connect(w.schedule_preview);row.addWidget(self.mask_only);outer.addLayout(row)
        row=QHBoxLayout()
        for title,fn in [('Rename layer',self.rename),('Duplicate layer',self.duplicate),('Group visible layers',self.group),('Ungroup selected',self.ungroup),('Reset selected mask / tone',self.clear)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        outer.addLayout(row)
        row=QHBoxLayout();row.addWidget(QLabel('Background'))
        self.colors=QComboBox();self.colors.addItems(['Sky blue','White','Light gray','Dark gray','Red']);self.colors.activated.connect(self.preset);row.addWidget(self.colors)
        self.recent=QComboBox();self.recent.addItems(w.db.get('recent_colors',[]));self.recent.activated.connect(lambda index:self.background(self.recent.itemText(index)));row.addWidget(self.recent)
        reset=QPushButton('Reset sky blue');reset.clicked.connect(lambda:self.background('#ADD8E6'));row.addWidget(reset);outer.addLayout(row)
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
            self.w.sync_controls()
