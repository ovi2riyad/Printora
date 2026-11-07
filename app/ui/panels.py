"""Resizable workspace panels with persistent large, small and icon layouts."""
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton,QMenu,QSplitter
from app.ui.icons import icon

def panel_state(db,key):
    states=db.get('panel_layout',{}) if db else {}
    return states.get(key,{}) if isinstance(states,dict) else {}

class AdaptivePanel(QWidget):
    mode_changed=Signal(str)
    def __init__(self,content,db,key,title,actions=(),navigation=False,default_width=350,minimum_width=280):
        super().__init__();self.content=content;self.db=db;self.key=key;self.navigation=navigation;self.default_width=default_width;self.splitter=None;self.restoring=False
        self.minimum_width=minimum_width;self.icon_buttons=[];self.setObjectName('adaptivePanel');self.setMinimumWidth(48)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        header=QHBoxLayout();header.setContentsMargins(2,0,2,0);layout.addLayout(header)
        self.title=QLabel(title);header.addWidget(self.title,1)
        self.mode_button=QToolButton();self.mode_button.setIcon(icon('menu'));self.mode_button.setAccessibleName(title+' panel size');self.mode_button.setToolTip('Panel size: Large, Small or Icons only. Drag the divider to resize.');self.mode_button.setPopupMode(QToolButton.InstantPopup)
        self.icon_buttons.append((self.mode_button,'menu'));menu=QMenu(self.mode_button);self.mode_actions={}
        for mode,label in [('large','Large panel'),('small','Small panel'),('icons','Icons only')]:
            action=menu.addAction(label);action.setCheckable(True);action.triggered.connect(lambda checked=False,m=mode:self.set_mode(m));self.mode_actions[mode]=action
        self.mode_button.setMenu(menu);header.addWidget(self.mode_button)
        self.rail=QWidget();rail=QVBoxLayout(self.rail);rail.setContentsMargins(2,0,2,0);rail.setSpacing(6)
        for label,name,callback in actions:
            button=QToolButton();button.setIcon(icon(name));button.setToolTip(label);button.setAccessibleName(label);button.clicked.connect(lambda checked=False,fn=callback:self.open_action(fn));rail.addWidget(button);self.icon_buttons.append((button,name))
        if not actions:
            button=QToolButton();button.setIcon(icon('settings'));button.setToolTip('Expand '+title);button.setAccessibleName('Expand '+title);button.clicked.connect(lambda:self.set_mode('small'));rail.addWidget(button);self.icon_buttons.append((button,'settings'))
        rail.addStretch();layout.addWidget(self.rail);layout.addWidget(content,1)
        state=panel_state(db,key);self.mode=state.get('mode','large');self.saved_width=state.get('width',default_width)
        self.restore_timer=QTimer(self);self.restore_timer.setSingleShot(True);self.restore_timer.timeout.connect(self.restore_width)
        self.apply_mode()

    def attach(self,splitter):
        self.splitter=splitter;splitter.splitterMoved.connect(self.remember_width);self.restore_timer.start(0)

    def refresh_icons(self,color):
        for button,name in self.icon_buttons:button.setIcon(icon(name,color))

    def showEvent(self,event):
        super().showEvent(event)
        # Inactive stacked pages start at a tiny geometry. Restore again after
        # activation, once the splitter actually has its workspace width.
        self.restore_timer.start(0)

    def open_action(self,callback):
        self.set_mode('small');callback()

    def apply_mode(self):
        collapsed=self.mode=='icons';self.title.setVisible(not collapsed);self.rail.setVisible(collapsed and not self.navigation);self.content.setVisible(not collapsed or self.navigation)
        self.setMinimumWidth(48 if collapsed else 130 if self.navigation else self.minimum_width)
        self.setMaximumWidth(52 if collapsed else 500 if self.navigation else 800)
        for mode,action in self.mode_actions.items():action.setChecked(mode==self.mode)
        self.mode_changed.emit(self.mode)

    def set_mode(self,mode):
        if mode not in self.mode_actions:return
        if self.mode!='icons':self.saved_width=max(self.minimumWidth(),self.size().width())
        self.mode=mode;self.apply_mode()
        target=52 if mode=='icons' else (164 if self.navigation else max(self.minimum_width,round(self.default_width*.78))) if mode=='small' else max(self.saved_width,self.default_width)
        self.resize_panel(target);self.persist()

    def resize_panel(self,width):
        if not self.splitter:return
        self.restoring=True
        sizes=self.splitter.sizes();index=self.splitter.indexOf(self)
        if index>=0:
            other=next((i for i in range(len(sizes)) if i!=index and not isinstance(self.splitter.widget(i),AdaptivePanel)),None)
            if other is not None:sizes[other]=max(200,sizes[other]+sizes[index]-width)
            sizes[index]=width;self.splitter.setSizes(sizes)
        self.restoring=False

    def restore_width(self):
        self.resize_panel(52 if self.mode=='icons' else self.saved_width)

    def remember_width(self,*_):
        if not self.restoring and self.mode!='icons':self.saved_width=self.size().width();self.persist()

    def persist(self):
        if self.mode!='icons':self.saved_width=self.size().width()
        if self.db:
            states=dict(self.db.get('panel_layout',{}));states[self.key]={'mode':self.mode,'width':max(48,min(800,self.saved_width))};self.db.set('panel_layout',states)

def splitter(*widgets):
    result=QSplitter(Qt.Horizontal);result.setChildrenCollapsible(False);result.setHandleWidth(7)
    for widget in widgets:result.addWidget(widget)
    for i,widget in enumerate(widgets):
        result.setStretchFactor(i,0 if isinstance(widget,AdaptivePanel) else 1)
        if isinstance(widget,AdaptivePanel):widget.attach(result)
    return result
