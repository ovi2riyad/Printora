"""Reusable bounded gallery for the full library and composition selectors."""
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QComboBox, QSlider, QLabel, QPushButton, QListWidgetItem, QListView)
from app.ui.selection import PhotoSelectionList
from app.ui.canvas import pixmap


class PhotoLibrary(QWidget):
    activated = Signal(str)

    def __init__(self, tray, maximum=None, parent=None, removed=False):
        super().__init__(parent)
        self.tray = tray
        self.removed=removed
        self.offset = 0
        self.rows = {}
        self.customer_lookup = None
        self.label_lookup = None
        outer = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search photo serial or name')
        outer.addWidget(self.search)
        row = QHBoxLayout()
        self.kind = QComboBox();self.kind.addItems(['All','Individual','Joint'])
        self.view = QComboBox();self.view.addItems(['Large thumbnails','Compact grid','List'])
        self.date = QComboBox();self.date.addItems(['All dates','Last 7 days','Last 30 days','Date unknown'])
        self.size = QSlider(Qt.Horizontal);self.size.setRange(60,180);self.size.setValue(110)
        for w in (self.kind,self.view,self.date,self.size):row.addWidget(w)
        outer.addLayout(row)
        self.list = PhotoSelectionList(maximum=maximum)
        self.list.setResizeMode(QListView.Adjust)
        outer.addWidget(self.list,1)
        self.selection = QLabel();self.selection.setWordWrap(True);outer.addWidget(self.selection)
        row = QHBoxLayout()
        for title, fn in [('Select visible',self.list.select_visible),('Clear selection',self.list.clear_selection),('Previous',lambda:self.page(-1)),('Next',lambda:self.page(1))]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        outer.addLayout(row)
        self.page_info=QLabel();outer.addWidget(self.page_info)
        self.search.textChanged.connect(self.reset_page)
        self.kind.currentIndexChanged.connect(self.reset_page)
        self.date.currentIndexChanged.connect(self.reset_page)
        self.view.currentIndexChanged.connect(self.presentation)
        self.size.valueChanged.connect(self.presentation)
        self.list.selection_updated.connect(self.update_selection)
        self.list.itemDoubleClicked.connect(lambda item:self.activated.emit(item.data(Qt.UserRole)))
        self.presentation()

    def reset_page(self,*_):self.offset=0;self.refresh()
    def page(self,delta):
        if delta>0 and len(self.rows)<200:return
        self.offset=max(0,self.offset+delta*200);self.refresh()
    def presentation(self,*_):
        mode=self.view.currentIndex();n=self.size.value() if mode!=1 else 70
        self.list.setViewMode(QListView.ListMode if mode==2 else QListView.IconMode)
        self.list.setIconSize(QSize(n,round(n*1.2)))
        self.list.setGridSize(QSize() if mode==2 else QSize(n+46,round(n*1.2)+66))
        self.refresh()
    def refresh(self,*_):
        text=self.search.text();ids=None
        if self.customer_lookup:ids=self.customer_lookup(text)
        rows=self.tray.query(text if ids is None else '',kind=self.kind.currentText(),offset=self.offset,date_filter=self.date.currentIndex(),ids=ids,deleted=self.removed)
        self.rows={p.id:p for p in rows};self.list.rebuilding=True;self.list.clear()
        for p in rows:
            w,h=p.size;customer=self.label_lookup(p.id) if self.label_lookup else ''
            title=f'{p.display_name}\n{p.kind} · {w} × {h} px'+ ('\n'+customer if customer else '')
            item=QListWidgetItem(QIcon(pixmap(p.thumbnail())),title)
            item.setCheckState(Qt.Checked if p.id in self.list.selected_ids else Qt.Unchecked)
            item.setData(Qt.UserRole,p.id);item.setToolTip(title+'\n'+(p.created_at or 'Earlier import — date unknown'))
            self.list.addItem(item)
        self.list.rebuilding=False;self.list.reapply()
        self.page_info.setText(f'Showing {len(rows)} results, starting at {self.offset+1}. Images load when needed.')
    def chosen(self):
        if self.removed:return self.tray.query(sort='oldest',deleted=True,limit=None,ids=self.list.selected_ids)
        return self.tray.by_ids(self.list.selected_ids)
    def update_selection(self):
        rows=self.chosen();self.selection.setText(f'{len(rows)} selected: '+', '.join(f'#{p.serial:06d}' for p in rows))
