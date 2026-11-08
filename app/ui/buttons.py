"""Native styled buttons that wrap their caption when a narrow panel needs it."""
from PySide6.QtCore import Qt,QRect,QSize
from PySide6.QtWidgets import QPushButton,QSizePolicy,QStyle,QStyleOptionButton,QStylePainter,QLabel

class ElidedLabel(QLabel):
    """Bound optional captions without letting long text cover adjacent actions."""
    def __init__(self,text='',parent=None):
        super().__init__(text,parent);self.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Preferred)
    def minimumSizeHint(self):return QSize(0,super().minimumSizeHint().height())
    def sizeHint(self):return QSize(min(160,super().sizeHint().width()),super().sizeHint().height())
    def setText(self,text):super().setText(text);self.setToolTip(text)
    def paintEvent(self,event):
        painter=QStylePainter(self)
        text=self.fontMetrics().elidedText(self.text(),Qt.ElideRight,max(0,self.contentsRect().width()))
        self.style().drawItemText(painter,self.contentsRect(),Qt.AlignVCenter|Qt.AlignLeft,self.palette(),self.isEnabled(),text,self.foregroundRole())

class WrappingButton(QPushButton):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        policy=QSizePolicy(QSizePolicy.Preferred,QSizePolicy.Preferred);policy.setHeightForWidth(True);self.setSizePolicy(policy)
    def minimumSizeHint(self):
        result=super().minimumSizeHint();result.setWidth(min(result.width(),80));return result
    def heightForWidth(self,width):
        bounds=self.fontMetrics().boundingRect(QRect(0,0,max(1,width-14),2000),Qt.TextWordWrap|Qt.AlignCenter,self.text())
        return max(super().sizeHint().height(),bounds.height()+16)
    def paintEvent(self,event):
        if not self.icon().isNull():super().paintEvent(event);return
        option=QStyleOptionButton();self.initStyleOption(option);caption=option.text;option.text=''
        painter=QStylePainter(self);painter.drawControl(QStyle.CE_PushButton,option)
        rect=self.rect().adjusted(7,1,-7,-1)
        self.style().drawItemText(painter,rect,Qt.AlignCenter|Qt.TextWordWrap|Qt.TextShowMnemonic,option.palette,self.isEnabled(),caption,self.foregroundRole())
