"""Selection belongs to photo IDs, independently of visible gallery rows."""
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QListWidget, QStyledItemDelegate, QAbstractItemView


class SelectionDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.data(Qt.UserRole) in self.parent().selected_ids:
            painter.save()
            painter.setPen(QPen(QColor('#095de5'), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(option.rect.adjusted(2, 2, -2, -2), 5, 5)
            badge = QRect(option.rect.right()-25, option.rect.top()+4, 21, 21)
            painter.fillRect(badge, QColor('#095de5'))
            painter.setPen(Qt.white)
            painter.drawText(badge, Qt.AlignCenter, '✓')
            painter.restore()


class PhotoSelectionList(QListWidget):
    selection_updated = Signal()

    def __init__(self, parent=None, maximum=None):
        super().__init__(parent)
        self.maximum = maximum
        self.selected_ids = set()
        self.rebuilding = False
        self.setSelectionMode(QAbstractItemView.ExtendedSelection if maximum != 1 else QAbstractItemView.SingleSelection)
        self.setItemDelegate(SelectionDelegate(self))
        self.setStyleSheet('QListWidget::item:selected {background:#d9e9ff;color:#102648;} QListWidget::item {padding:6px;}')
        self.itemSelectionChanged.connect(self.remember)
        self.itemChanged.connect(self.check_changed)

    def remember(self):
        if self.rebuilding:return
        visible = {self.item(i).data(Qt.UserRole) for i in range(self.count())}
        chosen = {i.data(Qt.UserRole) for i in self.selectedItems()}
        if self.maximum == 1 and chosen:self.selected_ids.clear()
        self.selected_ids.difference_update(visible)
        self.selected_ids.update(chosen)
        self.reapply()

    def check_changed(self, item):
        if self.rebuilding or not item.flags() & Qt.ItemIsUserCheckable:return
        photo_id = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            if self.maximum == 1:self.selected_ids.clear()
            self.selected_ids.add(photo_id)
        else:self.selected_ids.discard(photo_id)
        self.reapply()

    def reapply(self):
        self.rebuilding = True
        for i in range(self.count()):
            item = self.item(i)
            selected = item.data(Qt.UserRole) in self.selected_ids
            item.setSelected(selected)
            if item.flags() & Qt.ItemIsUserCheckable:item.setCheckState(Qt.Checked if selected else Qt.Unchecked)
        self.rebuilding = False
        self.viewport().update()
        self.selection_updated.emit()

    def clear_selection(self):
        self.selected_ids.clear()
        self.reapply()

    def select_visible(self):
        if self.maximum == 1:return
        self.selected_ids.update(self.item(i).data(Qt.UserRole) for i in range(self.count()))
        self.reapply()
