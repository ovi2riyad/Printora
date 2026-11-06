"""Optional offline studio utilities, using the existing library and worker queue."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QTabWidget,QLabel,
    QPushButton,QComboBox,QCheckBox,QLineEdit,QDoubleSpinBox,QListWidget,QFileDialog)
from app.ui.photo_library import PhotoLibrary
from app.ui.canvas import pixmap
from app.services import studio_tools as service


class StudioTools(QWidget):
    def __init__(self,manager):
        super().__init__();self.manager=manager;self.results=[]
        outer=QVBoxLayout(self);title=QLabel('Studio tools');title.setObjectName('title');outer.addWidget(title)
        self.tabs=QTabWidget();outer.addWidget(self.tabs,1)
        photos=QWidget();layout=QVBoxLayout(photos);self.gallery=PhotoLibrary(manager.w.tray,maximum=200);self.gallery.setMinimumHeight(240);layout.addWidget(self.gallery,1)
        row=QHBoxLayout();self.contact_names=QCheckBox('Photo names');self.contact_names.setChecked(True);self.contact_customers=QCheckBox('Customer names');self.contact_phones=QCheckBox('Customer mobiles')
        for w in (self.contact_names,self.contact_customers,self.contact_phones):row.addWidget(w)
        self.button(row,'Contact sheet PDF',self.contacts);layout.addLayout(row)
        row=QHBoxLayout();self.remove_bg=QCheckBox('Remove background');self.remove_bg.setChecked(True);row.addWidget(self.remove_bg)
        self.quality=QComboBox();self.quality.addItems(['balanced','fast','fine']);row.addWidget(self.quality)
        self.framing=QComboBox();self.framing.addItems(['balanced','document','fit','fill']);row.addWidget(self.framing)
        self.background=QLineEdit('#ADD8E6');self.background.setMaximumWidth(110);row.addWidget(self.background)
        self.recipe=QComboBox();row.addWidget(self.recipe);self.button(row,'Prepare selected batch',self.prepare);layout.addLayout(row)
        tones=QHBoxLayout();self.tones={}
        for field in ('brightness','contrast','saturation','sharpness'):
            box=QDoubleSpinBox();box.setRange(0,3);box.setSingleStep(.05);box.setValue(1);self.tones[field]=box;tones.addWidget(QLabel(field.title()));tones.addWidget(box)
        layout.addLayout(tones);layout.addWidget(QLabel('Each result needs visual review before saving. Open saved results in Portrait/Joint Maker for corrections.'))
        review=QHBoxLayout();self.result_list=QListWidget();self.result_list.setMaximumHeight(160);self.result_list.currentRowChanged.connect(self.preview_result);review.addWidget(self.result_list,1)
        self.preview=QLabel();self.preview.setFixedSize(150,160);self.preview.setAlignment(Qt.AlignCenter);review.addWidget(self.preview);layout.addLayout(review)
        row=QHBoxLayout();self.button(row,'Mark selected result reviewed',self.review);self.button(row,'Save reviewed results',self.save_reviewed);self.button(row,'Open saved result in maker',self.edit_result);self.button(row,'Add reviewed results to print session',self.send_session);layout.addLayout(row)
        self.tabs.addTab(photos,'Batch & contact sheets')
        orders=QWidget();layout=QVBoxLayout(orders);self.orders=QComboBox();layout.addWidget(self.orders)
        row=QHBoxLayout();self.button(row,'Save order QR image',self.save_qr);self.button(row,'Read QR image',self.read_qr);layout.addLayout(row)
        self.code=QLineEdit();self.code.setPlaceholderText('Scan or paste printora:order:…');self.code.returnPressed.connect(self.lookup);layout.addWidget(self.code);self.button(layout,'Find order from code',self.lookup)
        layout.addWidget(QLabel('QR codes contain only a local order ID. They resolve on this library or its restored backup.'))
        self.receipt_name=QCheckBox('Include customer name');self.receipt_mobile=QCheckBox('Include mobile');self.receipt_notes=QCheckBox('Include order notes')
        for w in (self.receipt_name,self.receipt_mobile,self.receipt_notes):layout.addWidget(w)
        row=QHBoxLayout();self.amount=QLineEdit();self.amount.setPlaceholderText('Optional total amount');self.currency=QLineEdit();self.currency.setPlaceholderText('Currency, e.g. BDT');self.currency.setMaxLength(12);row.addWidget(self.amount);row.addWidget(self.currency);layout.addLayout(row);self.button(layout,'Save receipt PDF',self.receipt);layout.addStretch(1);self.tabs.addTab(orders,'Order QR & receipts')
        calibration=QWidget();layout=QVBoxLayout(calibration);self.button(layout,'Export calibration PDF',self.calibrate)
        layout.addWidget(QLabel('Print at 100%, measure the 100 mm square, and save the measurements for your printer.\nCorrections are driver references; photo PDF dimensions stay exact.'))
        self.printer=QLineEdit();self.printer.setPlaceholderText('Printer name');layout.addWidget(self.printer)
        self.measured=[]
        for name in ('Measured width (mm)','Measured height (mm)'):
            layout.addWidget(QLabel(name));box=QDoubleSpinBox();box.setRange(50,150);box.setDecimals(2);box.setValue(100);layout.addWidget(box);self.measured.append(box)
        self.button(layout,'Save printer measurements',self.save_calibration);self.calibration_note=QLabel();self.calibration_note.setWordWrap(True);layout.addWidget(self.calibration_note);layout.addStretch(1);self.tabs.addTab(calibration,'Printer calibration')
        statistics=QWidget();layout=QVBoxLayout(statistics);self.stats=QLabel();self.stats.setWordWrap(True);layout.addWidget(self.stats);self.button(layout,'Refresh statistics',self.refresh_statistics);layout.addStretch(1);self.tabs.addTab(statistics,'Statistics')

    @property
    def w(self):return self.manager.w
    def button(self,layout,text,fn):
        b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b);return b
    def refresh(self):
        self.gallery.tray=self.w.tray;self.gallery.refresh();selected=self.orders.currentData();self.orders.clear()
        for order in self.manager.orders.search():self.orders.addItem(f'O{order["serial"]:06d} · {order["name"]}',order['id'])
        self.orders.setCurrentIndex(max(0,self.orders.findData(selected)));self.recipe.clear();self.recipe.addItem('Automatic sizes',None)
        from app.services.profiles import normalize_profile
        for p in self.w.db.profiles():
            value=normalize_profile(p,validate=False);self.recipe.addItem(value['name'],value)
        self.refresh_statistics()
    def target(self,label,extension):
        path,_=QFileDialog.getSaveFileName(self,label,'',f'{extension.upper()} files (*.{extension})')
        if not path:return None
        if not path.lower().endswith('.'+extension):path+='.'+extension
        try:
            from app.services.export_safety import check_export_target
            from app.services.storage import referenced_assets
            protected=referenced_assets(self.w.db.path.parent)
            protected.update(p.source for p in self.w.tray.items if p.source)
            return str(check_export_target(path,self.w.db.path.parent,self.w.db.conn,protected))
        except Exception as e:self.w.notify(str(e));return None
    def export(self,fn):self.w.run(fn,lambda path:self.w.notify('Saved: '+str(path)))
    def contacts(self):
        items=self.gallery.chosen()
        if not items:self.w.notify('Select photos first.');return
        path=self.target('Contact sheet','pdf')
        if not path:return
        details={}
        if self.contact_customers.isChecked() or self.contact_phones.isChecked():
            for item in items:
                rows=self.w.db.conn.execute('SELECT name,mobile FROM customers JOIN customer_photo_links ON customer_id=customers.id WHERE photo_id=?',(item.id,)).fetchall()
                details[item.id]={'name':', '.join(r[0] for r in rows),'mobile':', '.join(r[1] for r in rows)}
        flags=dict(include_names=self.contact_names.isChecked(),include_customer=self.contact_customers.isChecked(),include_mobile=self.contact_phones.isChecked())
        self.export(lambda:service.contact_sheet(items,path,details,**flags))
    def prepare(self):
        if any(r['job'] and not r['saved'] for r in self.results):self.w.notify('Save the current successful results before preparing another batch.');return
        items=self.gallery.chosen();options={k:v.value() for k,v in self.tones.items()};options.update(remove_background=self.remove_bg.isChecked(),background=self.background.text(),quality=self.quality.currentText(),framing=self.framing.currentText(),recipe=self.recipe.currentData())
        model=self.w.db.get('model_dir');root=self.w.db.path.parent
        self.w.run(lambda:service.batch_prepare(items,options,model,root),self.prepared)
    def prepared(self,results):
        self.results=results;self.result_list.clear()
        for r in results:self.result_list.addItem(f'#{r["serial"]:06d} · '+(r['error'] or 'Needs review'))
        if results:self.result_list.setCurrentRow(0)
    def current(self):
        i=self.result_list.currentRow();return self.results[i] if 0<=i<len(self.results) else None
    def preview_result(self,*_):
        r=self.current();self.preview.setPixmap(pixmap(r['preview']).scaled(150,160,Qt.KeepAspectRatio,Qt.SmoothTransformation)) if r and r['preview'] else self.preview.clear()
    def review(self):
        r=self.current()
        if r and r['job']:
            r['reviewed']=True;self.result_list.currentItem().setText(f'#{r["serial"]:06d} · Reviewed'+(' · Saved' if r['saved'] else ''))
    def save_reviewed(self):
        count=0
        for r in self.results:
            if r['reviewed'] and not r['saved']:
                self.w.db.save_job(r['job']);self.manager.link_job(r['job']);r['saved']=True;count+=1
        self.w.notify(f'Saved {count} reviewed jobs.');self.manager.refresh()
    def edit_result(self):
        r=self.current()
        if not r or not r['saved']:self.w.notify('Review and save this result first.');return
        self.manager.open_job(r['job'].id)
    def send_session(self):
        jobs=[self.w.db.load_job(r['job'].id) for r in self.results if r['reviewed'] and r['saved']]
        if not jobs:self.w.notify('Review and save results first.');return
        self.manager.multi.add_saved_jobs(jobs);self.manager.show(self.manager.multi)
    def save_qr(self):
        id=self.orders.currentData()
        if not id:self.w.notify('Create an order first.');return
        path=self.target('Order QR','png')
        if path:self.export(lambda:service.export_qr(id,path))
    def lookup(self):
        try:self.open_order(service.parse_qr(self.code.text()))
        except ValueError as e:self.w.notify(str(e))
    def open_order(self,id):
        self.manager.orders.get(id);self.manager.order_page.select_order(id);self.manager.show(self.manager.order_page)
    def read_qr(self):
        path,_=QFileDialog.getOpenFileName(self,'Read order QR','','Images (*.png *.jpg *.jpeg *.bmp *.webp)')
        if path:
            def done(id):
                try:self.open_order(id)
                except ValueError as e:self.w.notify(str(e))
            self.w.run(lambda:service.decode_qr(path),done)
    def receipt(self):
        id=self.orders.currentData()
        if not id:self.w.notify('Create an order first.');return
        order=self.manager.orders.get(id);job=self.manager.orders.load_job(id);path=self.target('Order receipt','pdf')
        flags=dict(include_name=self.receipt_name.isChecked(),include_mobile=self.receipt_mobile.isChecked(),include_notes=self.receipt_notes.isChecked(),amount=self.amount.text(),currency=self.currency.text())
        if path:self.export(lambda:service.receipt_pdf(order,job,path,**flags))
    def calibrate(self):
        path=self.target('Printer calibration','pdf')
        if path:self.export(lambda:service.calibration_sheet(path))
    def save_calibration(self):
        name=self.printer.text().strip()
        if not name:self.w.notify('Enter the printer name.');return
        profile=service.calibration_profile(*(b.value() for b in self.measured));profiles=self.w.db.get('printer_profiles',{});profiles[name]=profile;self.w.db.set('printer_profiles',profiles)
        self.calibration_note.setText(f'Saved {name}. Driver reference: X {profile["driver_x"]*100:.2f}%, Y {profile["driver_y"]*100:.2f}%.')
    def refresh_statistics(self):
        s=service.studio_statistics(self.w.db,self.w.tray)
        self.stats.setText(f'Active customers: {s["customers"]}\nOrders: {s["orders"]}\nPrepared photos (including removed): {s["prepared_photos"]}\nPhotos with unknown import date: {s["unknown_photo_dates"]}\nCopies in generated orders: {s["generated_copies"]}\nCopies in orders marked Completed: {s["completed_copies"]}\nCompletion is recorded by staff, not a printer sensor.\n\nMonthly orders (UTC):\n'+'\n'.join(f'{month}: {count}' for month,count in s['monthly_orders']))
