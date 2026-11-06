"""Order review, historical snapshots and reprint without reprocessing photos."""
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
    QListWidget,QPushButton,QTableWidget,QTableWidgetItem,QSpinBox,QDialog,QFormLayout,
    QDialogButtonBox,QFileDialog,QMessageBox)
from app.services.orders import STATUSES,write_order_pdf
from app.services.layout import resize_copies
from app.ui.print_options import PrintOptions


class OrderDialog(QDialog):
    def __init__(self,manager,job,parent=None):
        super().__init__(parent);self.manager=manager;self.job=job;self.customer_id=None;self.created=None
        self.setWindowTitle('Create order');form=QFormLayout(self);self.customer=QLabel('No customer (optional)');form.addRow('Customer',self.customer)
        choose=QPushButton('Choose / create customer');choose.clicked.connect(self.choose);form.addRow(choose)
        clear=QPushButton('Continue without customer');clear.clicked.connect(lambda:self.set_customer(None));form.addRow(clear)
        self.notes=QLineEdit();form.addRow('Notes',self.notes);self.error=QLabel();form.addRow(self.error)
        b=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);b.accepted.connect(self.accept);b.rejected.connect(self.reject);form.addRow(b)
    def set_customer(self,id):self.customer_id=id;self.customer.setText(self.manager.customers.get(id)['name'] if id else 'No customer (optional)')
    def choose(self):
        from app.ui.studio_manager import CustomerPicker
        d=CustomerPicker(self.manager.customers,self)
        if d.exec():self.set_customer(d.selected_id)
    def accept(self):
        try:self.created=self.manager.orders.create(self.job,self.customer_id,self.notes.text())
        except ValueError as e:self.error.setText(str(e));return
        super().accept()


class OrdersPage(QWidget):
    def __init__(self,manager):
        super().__init__();self.manager=manager;self.store=manager.orders;self.customer_id=None;self.rows=[];self.current_id=None;self.job=None;self.loading=False
        outer=QVBoxLayout(self);title=QLabel('Orders & Reprint');title.setObjectName('title');outer.addWidget(title)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Order ID, customer name or mobile');row.addWidget(self.search,1)
        self.status=QComboBox();self.status.addItems(['All statuses',*STATUSES]);row.addWidget(self.status)
        self.date=QComboBox();self.date.addItems(['All dates','Last 7 days','Last 30 days']);row.addWidget(self.date)
        clear=QPushButton('All customers');clear.clicked.connect(self.clear_customer);row.addWidget(clear);outer.addLayout(row)
        body=QHBoxLayout();self.list=QListWidget();body.addWidget(self.list,1)
        detail=QVBoxLayout();self.info=QLabel();self.info.setWordWrap(True);detail.addWidget(self.info)
        self.items=QTableWidget(0,3);self.items.setHorizontalHeaderLabels(['Composition','Size (mm)','Copies']);self.items.horizontalHeader().setStretchLastSection(True);detail.addWidget(self.items,1)
        self.options=PrintOptions();self.options.changed.connect(self.settings_changed);detail.addWidget(self.options)
        self.events=QComboBox();detail.addWidget(self.events);self.items.cellDoubleClicked.connect(self.preview_item);body.addLayout(detail,2);outer.addLayout(body,1)
        row=QHBoxLayout()
        for label,fn in [('From current job',self.from_current),('From saved job',self.from_saved),('Reprint / duplicate',self.reprint),('Generate PDF',self.export),('Open last PDF',self.open_pdf),('Completed',lambda:self.set_status('Completed')),('Cancel order',lambda:self.set_status('Cancelled'))]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        outer.addLayout(row);self.error=QLabel();self.error.setWordWrap(True);outer.addWidget(self.error)
        self.search.textChanged.connect(self.refresh);self.status.currentIndexChanged.connect(self.refresh);self.date.currentIndexChanged.connect(self.refresh);self.list.currentRowChanged.connect(self.details);self.refresh()
    def clear_customer(self):self.customer_id=None;self.refresh()
    def refresh(self,*_):
        old=self.current_id;self.rows=self.store.search(self.search.text(),self.customer_id,self.status.currentText() if self.status.currentIndex() else '',[None,7,30][self.date.currentIndex()]);self.list.blockSignals(True);self.list.clear()
        self.list.addItems([f'O{r["serial"]:06d} · {r["customer_name"] or "Unassigned"} · {r["status"]} · {r["created"]}' for r in self.rows]);index=next((i for i,r in enumerate(self.rows) if r['id']==old),0 if self.rows else -1);self.list.setCurrentRow(index);self.list.blockSignals(False);self.details()
    def details(self,*_):
        i=self.list.currentRow();self.loading=True;self.items.setRowCount(0);self.events.clear();self.job=None
        if not 0<=i<len(self.rows):self.current_id=None;self.info.setText('Create an order from a saved composition, or find a previous order to reprint.');self.loading=False;return
        order=self.rows[i];self.current_id=order['id'];self.job=self.store.load_job(order['id'])
        self.info.setText(f'O{order["serial"]:06d} · {order["customer_name"] or "No customer"} · {order["customer_mobile"]}\n{order["status"]} · {order["created"]}\n{order["notes"]}\nHistorical orders are preserved. Reprint creates a new draft with the original settings for review.')
        for index,p in enumerate(self.job.photos):
            self.items.insertRow(index)
            for column,text in enumerate((p.name,f'{p.width:g} × {p.height:g}')):
                item=QTableWidgetItem(text);item.setFlags(item.flags() & ~Qt.ItemIsEditable);self.items.setItem(index,column,item)
            quantity=QSpinBox();quantity.setRange(1,10000);quantity.setValue(p.quantity);quantity.setEnabled(order['status']=='Draft');quantity.valueChanged.connect(lambda n,i=index:self.quantity_changed(i,n));self.items.setCellWidget(index,2,quantity)
        self.options.load(self.job.print_settings);self.options.setEnabled(order['status']=='Draft');self.loading=False
        for event in self.store.events(self.current_id):self.events.addItem(f'{event["created"]} · {event["status"]} · {event["error"] or event["path"]}')
    def preview_item(self,row,column):
        if not self.job or not 0<=row<len(self.job.photos):return
        import copy
        from app.services.imaging import render_bordered_photo
        photo=copy.deepcopy(self.job.photos[row])
        self.manager.w.run(lambda:render_bordered_photo(photo,120),lambda im:self.manager.w.cropper.show_preview(im,photo.name))
    def quantity_changed(self,index,n):
        if self.loading or not self.job:return
        self.job.photos[index].quantity=n
        try:resize_copies(self.job);self.store.update_draft(self.current_id,self.job)
        except ValueError as e:self.error.setText(str(e))
    def settings_changed(self):
        if self.loading or not self.job:return
        self.job.print_settings.update(self.options.value());self.job.print_settings['auto_orientation']=False;self.job.placements=[]
        try:self.store.update_draft(self.current_id,self.job)
        except ValueError as e:self.error.setText(str(e))
    def create(self,job):
        d=OrderDialog(self.manager,job,self)
        if d.exec():self.select_order(d.created['id'])
    def select_order(self,id):
        self.customer_id=None;self.search.blockSignals(True);self.status.blockSignals(True)
        self.search.clear();self.status.setCurrentIndex(0);self.search.blockSignals(False);self.status.blockSignals(False);self.current_id=id;self.refresh()
    def from_current(self):
        if self.manager.w.photo and self.manager.w.photo.layers:self.create(self.manager.w.job)
        else:self.error.setText('Prepare or open a photo job first.')
    def from_saved(self):
        jobs=self.manager.w.db.jobs()
        if not jobs:self.error.setText('No saved jobs yet.');return
        from PySide6.QtWidgets import QInputDialog
        labels=[f'{i+1}. {name} · {updated}' for i,(_,name,updated) in enumerate(jobs)]
        value,ok=QInputDialog.getItem(self,'Saved composition','Choose a job',labels,0,False)
        if ok:self.create(self.manager.w.db.load_job(jobs[labels.index(value)][0]))
    def reprint(self):
        if not self.current_id:return
        try:new=self.store.duplicate(self.current_id);self.select_order(new['id'])
        except ValueError as e:self.error.setText(str(e))
    def set_status(self,status):
        if not self.current_id:return
        try:self.store.set_status(self.current_id,status);self.refresh()
        except ValueError as e:self.error.setText(str(e))
    def export(self):
        if not self.current_id:return
        order=self.store.get(self.current_id);folder=self.manager.w.db.get('output',str(Path.home()/'Documents'))
        path,_=QFileDialog.getSaveFileName(self,'Generate order PDF',str(Path(folder)/f'O{order["serial"]:06d}.pdf'),'PDF (*.pdf)')
        if not path:return
        try:event,job=self.store.begin_export(self.current_id,path)
        except ValueError as e:self.error.setText(str(e));return
        self.refresh();marker=self.store.marker(event)
        def done(result):self.store.finish_export(event,result);self.refresh();self.manager.refresh();self.error.setText('PDF ready. Print at Actual Size / 100%. Physical printing is not automatically confirmed.')
        def failed(_):self.store.finish_export(event,error='PDF generation failed; review the destination and source assets.');self.refresh()
        self.manager.w.run(lambda:write_order_pdf(job,path,event,marker),done,on_error=failed)
    def open_pdf(self):
        if not self.current_id:return
        events=[e for e in self.store.events(self.current_id) if e['status']=='Ready']
        if events and Path(events[-1]['path']).is_file():QDesktopServices.openUrl(QUrl.fromLocalFile(events[-1]['path']))
        else:self.error.setText('PDF not found. Create a reprint to generate a new artifact.')
