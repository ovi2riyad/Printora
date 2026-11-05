"""Shared print controls for the photo editor and sheet preview."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QFormLayout,QComboBox,QDoubleSpinBox,QSpinBox
from app.services.profiles import LAYOUTS


class PrintOptions(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        form = QFormLayout(self)
        form.setContentsMargins(0,0,0,0)
        self.paper = QComboBox()
        self.paper.addItems(['A4 portrait','A4 landscape'])
        self.layout = QComboBox()
        for key,title in LAYOUTS.items():self.layout.addItem(title,key)
        self.margin, self.gap_x, self.gap_y = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for control in (self.margin,self.gap_x,self.gap_y):
            control.setRange(0,80);control.setDecimals(2);control.setSingleStep(.2);control.setSuffix(' mm')
        self.rows,self.columns = QSpinBox(),QSpinBox()
        for control in (self.rows,self.columns):control.setRange(1,100);control.setValue(2)
        self.fields = dict(landscape=self.paper,layout=self.layout,margin=self.margin,gap_x=self.gap_x,gap_y=self.gap_y,rows=self.rows,columns=self.columns)
        for label,widget in [('Paper',self.paper),('Layout',self.layout),('Margin',self.margin),('Horizontal gap',self.gap_x),('Vertical gap',self.gap_y),('Columns',self.columns),('Rows',self.rows)]:form.addRow(label,widget)
        for control in self.fields.values():
            (control.currentIndexChanged if isinstance(control,QComboBox) else control.valueChanged).connect(self.on_change)
        self.load(dict(margin=10,gap_x=.2,gap_y=.2))

    def on_change(self,*_):
        self.rows.setEnabled(self.layout.currentData()=='custom')
        self.columns.setEnabled(self.layout.currentData()=='custom')
        self.changed.emit()

    def value(self):
        return dict(landscape=self.paper.currentIndex()==1,layout=self.layout.currentData(),
                    margin=self.margin.value(),gap_x=self.gap_x.value(),gap_y=self.gap_y.value(),
                    rows=self.rows.value(),columns=self.columns.value())

    def load(self,settings):
        for key,control in self.fields.items():
            control.blockSignals(True)
            if key=='landscape':control.setCurrentIndex(1 if settings.get(key) else 0)
            elif key=='layout':control.setCurrentIndex(max(0,control.findData(settings.get(key,'auto'))))
            else:control.setValue(settings.get(key,10 if key=='margin' else .2 if key.startswith('gap') else 2))
            control.blockSignals(False)
        self.rows.setEnabled(self.layout.currentData()=='custom')
        self.columns.setEnabled(self.layout.currentData()=='custom')
