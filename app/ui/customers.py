"""Customer forms and searchable profiles; all repository work stays on GUI thread."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,
    QTextEdit,QComboBox,QListWidget,QLabel,QPushButton,QDialog,QDialogButtonBox,QMessageBox)


class CustomerDialog(QDialog):
    def __init__(self,store,customer=None,parent=None):
        super().__init__(parent);self.store=store;self.customer=customer or {};self.result_customer=None
        self.setWindowTitle('Edit customer' if customer else 'New customer');form=QFormLayout(self);self.fields={}
        for key,label in [('name','Full name'),('mobile','Primary mobile (optional)'),('alternative_mobile','Alternative mobile'),('address','Address'),('email','Email'),('notes','Notes')]:
            field=QLineEdit(self.customer.get(key,''));self.fields[key]=field;form.addRow(label,field)
        self.error=QLabel();self.error.setWordWrap(True);form.addRow(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons);self.resize(550,400)
    def accept(self):
        values={k:w.text() for k,w in self.fields.items()}
        duplicates=self.store.duplicates(values['mobile'],self.customer.get('id'))
        if duplicates:
            answer=QMessageBox.question(self,'Shared mobile number','This number already belongs to a customer. Save a separate customer with the same number? Choose No to return and select the existing customer.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if answer!=QMessageBox.Yes:return
        try:self.result_customer=self.store.save(values,self.customer.get('id'))
        except ValueError as e:self.error.setText(str(e));return
        super().accept()


class CustomersPage(QWidget):
    changed=Signal()
    open_photos=Signal(str)
    open_orders=Signal(str)
    open_job=Signal(str)
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.rows=[];outer=QVBoxLayout(self)
        title=QLabel('Customers');title.setObjectName('title');outer.addWidget(title)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Name, mobile or C000001');row.addWidget(self.search,1)
        self.sort=QComboBox();self.sort.addItems(['Recent activity','Name','Registration date']);row.addWidget(self.sort)
        self.archived=QComboBox();self.archived.addItems(['Active customers','Archived customers']);row.addWidget(self.archived);outer.addLayout(row)
        body=QHBoxLayout();self.list=QListWidget();body.addWidget(self.list,1);self.details=QTextEdit();self.details.setReadOnly(True);body.addWidget(self.details,1);outer.addLayout(body,1)
        self.jobs=QComboBox();outer.addWidget(self.jobs)
        row=QHBoxLayout()
        for text,fn in [('Add customer',self.add),('Edit',self.edit),('Archive / recover',self.archive),('Photographs',self.photos),('Orders / reprint',self.orders),('Open composition',self.composition)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        outer.addLayout(row)
        self.search.textChanged.connect(self.refresh);self.sort.currentIndexChanged.connect(self.refresh);self.archived.currentIndexChanged.connect(self.refresh);self.list.currentRowChanged.connect(self.show_details);self.refresh()
    def selected(self):
        i=self.list.currentRow();return self.rows[i] if 0<=i<len(self.rows) else None
    def refresh(self,*_):
        old=self.selected();self.rows=self.store.search(self.search.text(),bool(self.archived.currentIndex()),['activity','name','created'][self.sort.currentIndex()]);self.list.clear()
        for c in self.rows:self.list.addItem(f'C{c["serial"]:06d} · {c["name"]} · {c["mobile"]}')
        self.list.setCurrentRow(next((i for i,c in enumerate(self.rows) if old and c['id']==old['id']),0 if self.rows else -1));self.show_details()
    def show_details(self,*_):
        c=self.selected();self.jobs.clear()
        if not c:self.details.setPlainText('Add a customer or search by name, mobile or ID. Registration is optional when importing.');return
        self.details.setPlainText('\n'.join(f'{k.replace("_"," ").title()}: {c[k]}' for k in ('name','mobile','alternative_mobile','address','email','notes','created','activity'))+f'\nLinked photos: {len(self.store.photo_ids(c["id"]))}')
        for id,name in self.store.conn.execute('SELECT j.id,j.name FROM jobs j JOIN customer_job_links l ON l.job_id=j.id WHERE l.customer_id=?',(c['id'],)):self.jobs.addItem(name,id)
    def add(self):
        d=CustomerDialog(self.store,parent=self)
        if d.exec():self.refresh();self.changed.emit()
    def edit(self):
        if self.selected() and CustomerDialog(self.store,self.selected(),self).exec():self.refresh();self.changed.emit()
    def archive(self):
        if self.selected():self.store.archive(self.selected()['id'],not self.selected()['archived']);self.refresh();self.changed.emit()
    def photos(self):
        if self.selected():self.open_photos.emit(self.selected()['id'])
    def orders(self):
        if self.selected():self.open_orders.emit(self.selected()['id'])
    def composition(self):
        if self.jobs.currentData():self.open_job.emit(self.jobs.currentData())
