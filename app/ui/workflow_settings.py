"""Per-workspace settings using the original controls, without duplicated values."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QPushButton,QFormLayout,QDialogButtonBox,QWidget,QScrollArea,QGridLayout,QLabel


class WorkflowSettings(QDialog):
    closed=Signal()
    def __init__(self,parent,title):
        super().__init__(parent);self.setWindowTitle(title+' — Settings');self.resize(580,720)
        if self.screen():
            area=self.screen().availableGeometry();self.resize(min(580,area.width()-30),min(720,area.height()-50))
        root=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();self.body=QVBoxLayout(content);scroll.setWidget(content);root.addWidget(scroll)
        self.actions=QGridLayout();self.body.addLayout(self.actions);self.action_count=0
        self.buttons=QDialogButtonBox(QDialogButtonBox.Close);self.buttons.rejected.connect(self.hide)
        self.status=QLabel();self.status.setWordWrap(True);root.addWidget(self.status)
        root.addWidget(self.buttons)
    def add_widget(self,widget):
        if isinstance(widget,QPushButton):
            self.actions.addWidget(widget,self.action_count//2,self.action_count%2);self.action_count+=1;return
        if isinstance(widget,QScrollArea):
            original=widget;widget=original.takeWidget();original.setParent(self);original.hide()
        self.body.insertWidget(self.body.count()-1,widget)
    def add_layout(self,layout):self.body.insertLayout(self.body.count()-1,layout)
    def open_settings(self):self.show();self.raise_();self.activateWindow()
    def hideEvent(self,event):super().hideEvent(event);self.closed.emit()


def move_rows(source,target,controls):
    """Move complete form rows; retain labels, signals and the single value owner."""
    for control in controls:
        if source.indexOf(control)<0:continue
        row=source.takeRow(control)
        label=row.labelItem.widget() if row.labelItem else None
        if label is not None:target.addRow(label,control)
        else:target.addRow(control)
