"""Compact overlays live outside the image scene and never enter exports."""
from PySide6.QtCore import Qt, QEvent, QTimer, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QSizePolicy


class FloatingFit(QToolButton):
    def __init__(self, view):
        super().__init__(view.viewport())
        self.view=view;self.setText('Fit');self.setAccessibleName('Fit photo preview')
        self.setToolTip('Fit preview · Ctrl+0');self.setFixedSize(42,28)
        self.setStyleSheet('QToolButton {background:rgba(24,40,68,220);color:#edf4ff;border:1px solid #7187a8;border-radius:6px;}')
        self.clicked.connect(lambda:view.fitInView(view.sceneRect(),Qt.KeepAspectRatio))
        view.viewport().installEventFilter(self);self.place();self.show()
    def place(self):self.move(10,max(8,self.parentWidget().height()-self.height()-10));self.raise_()
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Resize,QEvent.Show):self.place()
        return super().eventFilter(obj,event)


class CompactEditorPage(QWidget):
    def __init__(self,owner):super().__init__();self.owner=owner
    def fit_width(self,width):
        w=self.owner
        if not hasattr(w,'auto_soften'):return
        from app.ui.icons import icon
        w.workflow_title.setVisible(width>=720)
        actions=[(w.choose_photo_button,'Choose photo','import'),(w.top_preview,'Preview PDF','recipes')]
        actions += [(button,title,name) for button,title,name in getattr(w,'session_actions',[])]
        for button,title,name in actions:
            compact=width<900;button.setText('' if compact else title);button.setIcon(icon(name));button.setToolTip(title);button.setAccessibleName(title)
            button.setMinimumWidth(0);button.setMaximumWidth(34 if compact else 16777215)
        for button in w.quick_quantities:button.setVisible(width>=620 or button.text() in ('2','4'))
        w.auto_soften.setText('' if width<620 else 'Auto soften');w.auto_soften.setIcon(icon('portrait'));w.auto_soften.setAccessibleName('Auto portrait softener')
        w.brush_caption.setVisible(width>=650);w.shape_caption.setVisible(width>=650)
        w.brush_size.setMaximumWidth(64 if width<650 else 80)


class FloatingPanelHost(QWidget):
    def __init__(self, canvas_area, panel):
        super().__init__();self.panel=panel
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.addWidget(canvas_area)
        panel.setParent(self);panel.setObjectName('floatingPhotoControls')
        self.refresh_theme()
        panel.mode_changed.connect(lambda *_:QTimer.singleShot(0,self.arrange))
        panel.show();QTimer.singleShot(0,self.arrange)
    def refresh_theme(self):
        dark=self.window().property('themeMode')!='Light'
        background='26,41,68' if dark else '246,249,255'
        text='#edf4ff' if dark else '#17243b'
        self.panel.setStyleSheet(f'QWidget#floatingPhotoControls {{border:1px solid #7187a8;border-radius:10px;background:rgba({background},218);}}'
            f'QWidget#floatingPhotoControls QWidget {{background:transparent;color:{text};}}'
            f'QWidget#floatingPhotoControls QAbstractSpinBox,QWidget#floatingPhotoControls QComboBox,QWidget#floatingPhotoControls QPushButton {{background:rgba({background},235);}}')
    def minimumSizeHint(self):return QSize(240,60)
    def sizeHint(self):return QSize(800,560)
    def arrange(self):
        panel=self.panel;collapsed=panel.mode=='icons'
        panel.rail.hide()
        panel.mode_button.setText('Edit' if collapsed else '')
        panel.mode_button.setToolButtonStyle(Qt.ToolButtonTextOnly if collapsed else Qt.ToolButtonIconOnly)
        width=52 if collapsed else min(280 if panel.mode=='large' else 248,max(160,self.width()-24))
        panel.setMinimumWidth(48 if collapsed else 160)
        panel.setMaximumWidth(52 if collapsed else 310)
        panel.setGeometry(max(4,self.width()-width-10),8,width,42 if collapsed else max(80,self.height()-16))
        panel.raise_()
    def resizeEvent(self,event):super().resizeEvent(event);self.arrange()
