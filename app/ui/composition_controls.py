"""Physical framing controls shared by portrait and joint compositions."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QFormLayout,QComboBox,QDoubleSpinBox,QCheckBox,QPushButton,QInputDialog


class CompositionControls(QWidget):
    apply_requested=Signal(str,object)
    guides_changed=Signal(bool)

    def __init__(self,db,parent=None):
        super().__init__(parent);self.db=db
        form=QFormLayout(self);self.fields={}
        self.mode=QComboBox();self.mode.addItems(['Balanced','Document','Custom']);form.addRow('Framing mode',self.mode)
        for key,label,default,high in [('top','Top margin (mm)',2,100),('bottom','Bottom margin (mm)',2,100),('left','Left margin (mm)',2,100),('right','Right margin (mm)',2,100),('subject_scale','Subject scale',1,3),('head_position','Head center (height fraction)',.28,1)]:
            w=QDoubleSpinBox();w.setRange(.1 if key=='subject_scale' else 0,high);w.setDecimals(2);w.setSingleStep(.05 if high<=3 else .5);w.setValue(default);self.fields[key]=w;form.addRow(label,w)
        for key,label,items in [('horizontal','Horizontal alignment',['Left','Center','Right']),('vertical','Vertical alignment',['Top','Center','Bottom'])]:
            w=QComboBox();w.addItems(items);w.setCurrentIndex(1);self.fields[key]=w;form.addRow(label,w)
        self.guides=QCheckBox('Safe area (screen only)');self.guides.setChecked(True);self.guides.toggled.connect(self.guides_changed);form.addRow(self.guides)
        self.shoulder=QDoubleSpinBox();self.shoulder.setRange(0,1);self.shoulder.setSingleStep(.05);self.shoulder.setValue(.85)
        self.use_shoulder=QCheckBox('Use shoulder / lower-edge anchor');form.addRow(self.use_shoulder,self.shoulder)
        apply=QPushButton('Apply / reset framing');apply.clicked.connect(lambda:self.apply_requested.emit(self.mode.currentText().lower(),self.value()));form.addRow(apply)
        equal=QPushButton('Equalize margins');equal.clicked.connect(self.equalize);form.addRow(equal)
        self.presets=QComboBox();form.addRow('Composition preset',self.presets)
        save=QPushButton('Save framing preset');save.clicked.connect(self.save_preset);form.addRow(save)
        load=QPushButton('Load selected preset');load.clicked.connect(self.load_preset);form.addRow(load);self.refresh_presets()
    def value(self):
        value={k:(w.currentIndex()/2 if isinstance(w,QComboBox) else w.value()) for k,w in self.fields.items()}
        if self.use_shoulder.isChecked():value['shoulder_position']=self.shoulder.value()
        return value
    def load(self,values):
        for k,w in self.fields.items():
            v=values.get(k,.5 if k in ('horizontal','vertical') else .28 if k=='head_position' else 1 if k=='subject_scale' else 2)
            if isinstance(w,QComboBox):w.setCurrentIndex(round(v*2))
            else:w.setValue(v)
        self.mode.setCurrentText(values.get('mode','balanced').title())
        self.use_shoulder.setChecked(values.get('shoulder_position') is not None);self.shoulder.setValue(values['shoulder_position'] if values.get('shoulder_position') is not None else .85)
    def equalize(self):
        for k in ('bottom','left','right'):self.fields[k].setValue(self.fields['top'].value())
    def refresh_presets(self):
        self.presets.clear();self.presets.addItems(sorted(self.db.get('composition_presets',{})))
    def save_preset(self):
        name,ok=QInputDialog.getText(self,'Composition preset','Name')
        if ok and name.strip():
            rows=self.db.get('composition_presets',{});rows[name.strip()]=dict(self.value(),mode=self.mode.currentText().lower());self.db.set('composition_presets',rows);self.refresh_presets()
    def load_preset(self):
        value=self.db.get('composition_presets',{}).get(self.presets.currentText())
        if value:self.load(value);self.apply_requested.emit(value.get('mode','balanced'),value)
