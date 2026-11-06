"""Mixed-size multi-person printing with reviewed snapshots and saved placements."""
import copy
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,
    QTableWidgetItem,QSpinBox,QComboBox,QCheckBox,QDialog,QListWidget,QDialogButtonBox,
    QInputDialog,QFileDialog,QMessageBox,QAbstractItemView)
from app.models.domain import Job
from app.services.print_sessions import PrintSessionStore,add_composition,choose_orientation
from app.services.layout import resize_copies,validate_layout,page_size
from app.services.imaging import render_photo,resolution_warnings
from app.services.pdf import export_pdf
from app.ui.photo_library import PhotoLibrary
from app.ui.print_options import PrintOptions
from app.ui.canvas import PrintCanvas


class MultiPhotoPrint(QWidget):
    def __init__(self,manager):
        super().__init__();self.manager=manager;self.store=PrintSessionStore(manager.w.db);self.job=self.empty_job();self.session_id=None;self.loading=False;self.queue=[];self.review_job_id=None;self.edit_photo_id=None
        outer=QVBoxLayout(self);title=QLabel('Multi Photo Print');title.setObjectName('title');outer.addWidget(title)
        row=QHBoxLayout()
        for title,fn in [('Add saved compositions',self.add_saved),('Prepare library photos',self.add_library),('New session',self.new),('Save session',self.save_as),('Open session',self.open_session),('Create order',self.create_order),('Export PDF',self.export)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        outer.addLayout(row);body=QHBoxLayout()
        left=QVBoxLayout();self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Composition','Size (mm)','Copies']);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.horizontalHeader().setStretchLastSection(True);left.addWidget(self.table,1)
        row=QHBoxLayout()
        for title,fn in [('Edit/review',self.edit),('Duplicate',self.duplicate),('Remove',self.remove),('Up',lambda:self.reorder(-1)),('Down',lambda:self.reorder(1)),('Clear',self.clear)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        left.addLayout(row);row=QHBoxLayout();self.all_quantity=QSpinBox();self.all_quantity.setRange(1,10000);self.all_quantity.setValue(4);row.addWidget(self.all_quantity)
        apply=QPushButton('Apply copies to all');apply.clicked.connect(self.apply_quantity);row.addWidget(apply);left.addLayout(row)
        row=QHBoxLayout()
        for n in (2,4,6,8,10,12):
            b=QPushButton(f'{n} copies');b.clicked.connect(lambda checked=False,n=n:self.all_quantity.setValue(n));row.addWidget(b)
        left.addLayout(row)
        self.options=PrintOptions();self.options.load(self.job.print_settings);self.options.changed.connect(self.settings_changed);left.addWidget(self.options)
        self.auto_orientation=QCheckBox('Choose paper orientation with fewer pages');self.auto_orientation.setChecked(True);left.addWidget(self.auto_orientation)
        self.options.paper.currentIndexChanged.connect(lambda *_:self.auto_orientation.setChecked(False))
        arrange=QPushButton('Arrange / reset automatic layout');arrange.clicked.connect(self.arrange);left.addWidget(arrange);body.addLayout(left,1)
        right=QVBoxLayout();self.pages=QComboBox();self.pages.currentIndexChanged.connect(self.render);right.addWidget(self.pages);self.canvas=PrintCanvas();self.canvas.changed.connect(self.placement_changed);right.addWidget(self.canvas,1);body.addLayout(right,1);outer.addLayout(body,1)
        self.summary=QLabel('Add saved compositions, or prepare and review library photos.');self.summary.setWordWrap(True);outer.addWidget(self.summary)
    def empty_job(self):return Job(name='Multi Photo Print',print_settings=dict(margin=10,gap_x=.2,gap_y=.2,landscape=False,layout='auto',rows=2,columns=2,dpi=300,enforce_margins=True))
    def selected(self):
        row=self.table.currentRow();return row if 0<=row<len(self.job.photos) else None
    def refresh(self):
        self.loading=True;old=self.table.currentRow();self.table.setRowCount(0)
        for i,p in enumerate(self.job.photos):
            self.table.insertRow(i)
            for column,text in enumerate((p.name,f'{p.width:g} × {p.height:g}')):
                item=QTableWidgetItem(text);item.setFlags(item.flags() & ~Qt.ItemIsEditable);self.table.setItem(i,column,item)
            qty=QSpinBox();qty.setRange(1,10000);qty.setValue(p.quantity);qty.valueChanged.connect(lambda value,i=i:self.quantity(i,value));self.table.setCellWidget(i,2,qty)
        self.table.selectRow(max(0,min(old,len(self.job.photos)-1)));self.options.load(self.job.print_settings)
        current=self.pages.currentIndex();self.pages.blockSignals(True);self.pages.clear();self.pages.addItems([f'Page {i+1} of {self.job.page_count}' for i in range(self.job.page_count)]);self.pages.setCurrentIndex(max(0,min(current,self.job.page_count-1)));self.pages.blockSignals(False);self.loading=False
        pw,ph=page_size(self.job.print_settings);area=(pw-2*self.job.print_settings['margin'])*(ph-2*self.job.print_settings['margin'])*self.job.page_count-sum(p.width*p.height*p.quantity for p in self.job.photos)
        self.summary.setText(f'{len(self.job.photos)} compositions · {sum(p.quantity for p in self.job.photos)} copies · {self.job.page_count} pages · A4 {"landscape" if self.job.print_settings.get("landscape") else "portrait"}\nUnused printable area: {max(0,area):.0f} mm² (may be fragmented). Photo sizes and orientations are preserved. Grid modes give each composition its own page group.')
        if self.job.placements:self.render()
        else:self.canvas.scene().clear()
    def persist(self):
        if self.job.photos or self.session_id:
            self.job.print_settings['auto_orientation']=self.auto_orientation.isChecked();self.session_id=self.store.save(self.job,self.session_id)
    def changed(self):
        try:
            if self.job.placements:resize_copies(self.job)
            elif self.job.photos:self.job.print_settings,self.job.placements,self.job.page_count=choose_orientation(self.job.photos,self.job.print_settings,self.auto_orientation.isChecked())
            self.persist();self.refresh()
        except ValueError as e:self.summary.setText(str(e))
    def quantity(self,index,value):
        if not self.loading:self.job.photos[index].quantity=value;self.changed()
    def apply_quantity(self):
        for p in self.job.photos:p.quantity=self.all_quantity.value()
        self.changed()
    def settings_changed(self):
        if self.loading:return
        self.job.print_settings.update(self.options.value());self.job.placements=[];self.changed()
    def arrange(self):
        if not self.job.photos:return
        if self.job.placements and QMessageBox.question(self,'Reset placements','Replace current placements with automatic layout?',QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return
        self.job.placements=[];self.changed()
    def render(self,*_):
        if self.loading or self.manager.w.busy or not self.job.placements or self.manager.w.stack.currentWidget() is not self:return
        page=max(0,self.pages.currentIndex());snapshot=copy.deepcopy(self.job);needed={r.photo_id for r in snapshot.placements if r.page==page}
        self.manager.w.run(lambda:{p.id:render_photo(p,120) for p in snapshot.photos if p.id in needed},lambda images:self.canvas.display(self.job,page,images,vector_borders=True))
    def placement_changed(self):
        try:validate_layout(self.job);self.persist();self.summary.setText('Manual placements saved. Reopening the session preserves them.')
        except ValueError as e:self.summary.setText(str(e))
    def add_saved_jobs(self,jobs):
        for job in jobs:
            for photo in job.photos:add_composition(self.job,photo,job.id)
        self.changed()
    def add_saved(self):
        rows=self.manager.w.db.jobs();d=QDialog(self);d.setWindowTitle('Select saved portrait/joint compositions');outer=QVBoxLayout(d);listing=QListWidget();listing.setSelectionMode(QAbstractItemView.ExtendedSelection);listing.addItems([f'{name} · {date}' for id,name,date in rows]);outer.addWidget(listing)
        buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject);outer.addWidget(buttons);d.resize(700,500)
        if d.exec():self.add_saved_jobs([self.manager.w.db.load_job(rows[listing.row(item)][0]) for item in listing.selectedItems()])
    def add_library(self):
        d=QDialog(self);d.setWindowTitle('Choose library photos to prepare and review');outer=QVBoxLayout(d);outer.addWidget(QLabel('Each selected photo opens in its maker. Review it, then click Add reviewed photo.'))
        gallery=PhotoLibrary(self.manager.w.tray);outer.addWidget(gallery);buttons=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject);outer.addWidget(buttons);d.resize(950,700)
        if d.exec():self.queue=gallery.chosen();self.next_prepared()
    def next_prepared(self):
        if not self.queue:self.manager.show(self);return
        item=self.queue[0];self.edit_photo_id=None
        if self.manager.w.start_workflow('joint' if item.kind=='Joint' else 'portrait'):
            self.queue.pop(0)
            self.review_job_id=self.manager.w.job.id;self.manager.w.load_prepared([item])
    def accept_reviewed(self):
        w=self.manager.w
        if w.busy or not w.photo or not w.photo.layers:return
        if w.job.id==self.review_job_id and self.edit_photo_id:
            index=next((i for i,p in enumerate(self.job.photos) if p.id==self.edit_photo_id),None)
            if index is None:w.notify('This session item was removed. Add the reviewed photo as a new item.');return
            p=copy.deepcopy(w.photo);p.id=self.edit_photo_id;self.job.photos[index]=p;self.job.placements=[]
        else:add_composition(self.job,w.photo,w.job.id)
        w.save_job();w.dirty=False;self.review_job_id=None;self.edit_photo_id=None;self.changed()
        if self.queue:self.next_prepared()
        else:self.manager.show(self)
    def edit(self):
        i=self.selected()
        if i is None or not self.manager.w.save_before_leave():return
        w=self.manager.w;p=copy.deepcopy(self.job.photos[i]);self.edit_photo_id=p.id;w.job=Job(name=p.name+' (review)',photos=[p]);self.review_job_id=w.job.id;w.photo=p;w.mode='portrait' if p.kind=='Individual' else 'joint';w.undo.clear();w.redo.clear();w.dirty=False;w.sync_controls();w.stack.setCurrentIndex(1)
    def duplicate(self):
        i=self.selected()
        if i is not None:add_composition(self.job,self.job.photos[i]);self.changed()
    def remove(self):
        selected={i.row() for i in self.table.selectionModel().selectedRows()}
        self.job.photos[:]=[p for i,p in enumerate(self.job.photos) if i not in selected];self.changed()
    def reorder(self,delta):
        i=self.selected()
        if i is not None and 0<=i+delta<len(self.job.photos):self.job.photos[i],self.job.photos[i+delta]=self.job.photos[i+delta],self.job.photos[i];self.persist();self.refresh();self.table.selectRow(i+delta)
    def clear(self):
        if self.job.photos and QMessageBox.question(self,'Clear session','Start an empty session? The saved session remains available.',QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return
        self.new()
    def new(self):self.job=self.empty_job();self.session_id=None;self.queue=[];self.auto_orientation.setChecked(True);self.refresh()
    def save_as(self):
        name,ok=QInputDialog.getText(self,'Save print session','Session name',text=self.job.name)
        if ok and name.strip():
            self.job.name=name.strip()
            try:self.persist();self.summary.setText('Session saved on this PC.')
            except ValueError as e:self.summary.setText(str(e))
    def open_session(self):
        rows=self.store.list()
        if not rows:return
        labels=[f'{i+1}. {r["name"]} · {r["updated"]}' for i,r in enumerate(rows)]
        name,ok=QInputDialog.getItem(self,'Open session','Saved sessions',labels,0,False)
        if ok:self.load_session(rows[labels.index(name)]['id'])
    def load_session(self,id):self.session_id=id;self.job=self.store.load(id);self.auto_orientation.setChecked(self.job.print_settings.get('auto_orientation',True));self.refresh()
    def create_order(self):
        if self.job.photos:self.manager.order_page.create(self.job);self.manager.show(self.manager.order_page)
    def export(self):
        try:validate_layout(self.job)
        except ValueError as e:self.summary.setText(str(e));return
        path,_=QFileDialog.getSaveFileName(self,'Multi Photo Print PDF',str(Path(self.manager.w.db.get('output',str(Path.home()/'Documents')))/'multi-photo.pdf'),'PDF (*.pdf)')
        if not path:return
        from app.services.export_safety import check_export_target
        try:check_export_target(path,self.manager.w.db.path.parent,self.manager.w.db.conn)
        except ValueError as e:self.summary.setText(str(e));return
        snapshot=copy.deepcopy(self.job);warnings=[s for p in snapshot.photos for s in resolution_warnings(p)]
        if warnings and QMessageBox.question(self,'Image resolution','\n'.join(warnings[:12])+'\nContinue?',QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return
        self.persist();self.manager.w.run(lambda:export_pdf(snapshot,path,dpi=int(snapshot.print_settings.get('dpi',300))),lambda _:self.summary.setText('PDF ready. Print at Actual Size / 100%. Create an order to retain reprint history.'))
