"""Studio module coordinator; the existing single-photo editor remains intact."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QComboBox,QInputDialog,QMessageBox,QDialog,QListWidget,QLineEdit,QDialogButtonBox,QStyle,QFrame,QScrollArea)
from app.services.customers import CustomerStore
from app.ui.customers import CustomersPage,CustomerDialog
from app.ui.photo_library import PhotoLibrary
from app.ui.canvas import pixmap
from app.services.record_recovery import recoverable_record,checked_document


class CustomerPicker(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.selected_id=None;self.rows=[];self.setWindowTitle('Choose customer (optional)');outer=QVBoxLayout(self)
        self.search=QLineEdit();self.search.setPlaceholderText('Search name, mobile or customer ID');outer.addWidget(self.search)
        self.list=QListWidget();outer.addWidget(self.list)
        new=QPushButton('Create new customer');new.clicked.connect(self.create);outer.addWidget(new)
        b=QDialogButtonBox(QDialogButtonBox.Open|QDialogButtonBox.Cancel);b.accepted.connect(self.accept);b.rejected.connect(self.reject);outer.addWidget(b);self.search.textChanged.connect(self.refresh);self.refresh();self.resize(650,500)
    def refresh(self,*_):
        self.rows=self.store.search(self.search.text());self.list.clear()
        self.list.addItems([f'C{c["serial"]:06d} · {c["name"]} · {c["mobile"]}' for c in self.rows])
    def create(self):
        d=CustomerDialog(self.store,parent=self)
        if d.exec():self.selected_id=d.result_customer['id'];super().accept()
    def accept(self):
        i=self.list.currentRow()
        if i>=0:self.selected_id=self.rows[i]['id'];super().accept()


class LibraryPage(QWidget):
    def __init__(self,manager):
        super().__init__();self.manager=manager;self.customer_id=None;outer=QVBoxLayout(self)
        title=QLabel('Photo Library');title.setObjectName('title');outer.addWidget(title)
        self.gallery=PhotoLibrary(manager.w.tray);self.gallery.customer_lookup=self.lookup;self.gallery.label_lookup=manager.customers.names_for_photo;self.gallery.activated.connect(self.preview);outer.addWidget(self.gallery,1)
        row=QHBoxLayout()
        for label,fn in [('Portrait',lambda:self.use('portrait')),('Joint',lambda:self.use('joint')),('Assign customer',self.assign),('Clear customer filter',self.clear_filter),('Bulk rename',self.rename),('Individual',lambda:self.classify('Individual')),('Joint type',lambda:self.classify('Joint')),('Remove',self.remove)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        outer.addLayout(row)
        unlink=QPushButton('Unlink selected photos from filtered customer');unlink.clicked.connect(self.unlink);outer.addWidget(unlink)
    def lookup(self,text):
        if self.customer_id:
            ids=self.manager.customers.photo_ids(self.customer_id)
            return ids & {p.id for p in self.manager.w.tray.query(text,limit=None)} if text else ids
        if text:
            matches=self.manager.customers.matching_photo_ids(text)
            if matches:return matches|{p.id for p in self.manager.w.tray.query(text)}
        return None
    def clear_filter(self):self.customer_id=None;self.gallery.reset_page()
    def unlink(self):
        if not self.customer_id:self.manager.w.notify('Open a customer profile and choose Photographs before unlinking their photos.');return
        self.manager.customers.unlink_photos(self.customer_id,set(self.gallery.list.selected_ids));self.gallery.list.clear_selection();self.gallery.refresh()
    def use(self,mode):
        items=self.gallery.chosen()
        if len(items) not in ((1,) if mode=='portrait' else (1,2)):self.manager.w.notify('Choose one portrait, or one combined/two separate joint photos.');return
        self.manager.w.use_crops(mode,items)
    def assign(self):
        d=CustomerPicker(self.manager.customers,self)
        if d.exec():
            try:self.manager.customers.assign_photos(d.selected_id,self.gallery.list.selected_ids,self.manager.w.tray);self.gallery.refresh()
            except ValueError as e:self.manager.w.notify(str(e))
    def rename(self):
        selected=self.gallery.chosen()
        if not selected:return
        prefix,ok=QInputDialog.getText(self,'Bulk rename',f'Rename {len(selected)} selected photos with prefix + permanent serial. Prefix:')
        if ok and prefix.strip():
            for p in selected:self.manager.w.tray.rename(p,f'{prefix.strip()} {p.serial:06d}')
            self.gallery.refresh()
    def classify(self,kind):self.manager.w.tray.set_kind(self.gallery.list.selected_ids,kind);self.gallery.refresh()
    def remove(self):
        ids=set(self.gallery.list.selected_ids)
        if ids and QMessageBox.question(self,'Remove library photos',f'Hide {len(ids)} selected photos? Saved jobs retain their files; recovery is available in Cropper.',QMessageBox.Yes|QMessageBox.Cancel)==QMessageBox.Yes:
            self.manager.w.tray.remove(ids);self.gallery.list.clear_selection();self.gallery.refresh()
    def preview(self,id):
        item=self.gallery.rows[id]
        def load():
            im=item.image;im.thumbnail((850,650));return im
        self.manager.w.run(load,lambda im:self.manager.w.cropper.show_preview(im,item.display_name))


class StudioManager:
    def __init__(self,w):
        self.w=w;self.customers=CustomerStore(w.db);self.customers.reconcile(w.tray)
        from app.services.orders import OrderStore
        from app.ui.orders import OrdersPage
        self.orders=OrderStore(w.db);self.order_page=OrdersPage(self);w.stack.addWidget(self.order_page)
        from app.ui.multi_photo_print import MultiPhotoPrint
        self.multi=MultiPhotoPrint(self);w.stack.addWidget(self.multi)
        bar=QHBoxLayout();review=QPushButton('Add reviewed photo to session');review.clicked.connect(self.multi.accept_reviewed);bar.addWidget(review);w.stack.widget(1).layout().insertLayout(2,bar)
        from app.ui.editor_tools import EditorTools
        w.editor_tools=EditorTools(w);selection_scroll=QScrollArea();selection_scroll.setWidgetResizable(True);selection_scroll.setWidget(w.editor_tools);w.editor_tabs.addTab(selection_scroll,'Select / Mask')
        order=QPushButton('Create order');order.clicked.connect(lambda:self.order_page.create(w.job) if w.photo and w.photo.layers else w.notify('Prepare a composition first.'));bar.addWidget(order)
        self.customer_page=CustomersPage(self.customers);self.library=LibraryPage(self)
        self.customer_page.changed.connect(self.refresh);self.customer_page.open_photos.connect(self.customer_photos);self.customer_page.open_job.connect(self.open_job)
        self.customer_page.open_orders.connect(self.customer_orders)
        w.stack.addWidget(self.customer_page);w.stack.addWidget(self.library)
        row=QHBoxLayout();self.import_customer=QLabel('Import customer: unassigned (optional)');row.addWidget(self.import_customer,1)
        choose=QPushButton('Choose / create customer');choose.clicked.connect(self.choose_import_customer);row.addWidget(choose)
        clear=QPushButton('Unassigned');clear.clicked.connect(self.clear_import_customer);row.addWidget(clear);w.cropper.layout().insertLayout(2,row)
        self.import_customer_id=None
        w.cropper.on_sources_imported=lambda paths:self.customers.assign_sources(self.import_customer_id,paths,w.tray)
        w.cropper.on_crops_saved=lambda:self.customers.reconcile(w.tray)
        from app.ui.studio_tools import StudioTools
        self.tools=StudioTools(self);w.stack.addWidget(self.tools)
        from app.ui.hardware import HardwareHub
        w.hardware=HardwareHub(w)
        self.dashboard=self.make_dashboard();old=w.stack.widget(0);w.stack.removeWidget(old);w.stack.insertWidget(0,self.dashboard);old.deleteLater();w.stack.setCurrentIndex(0)
    def clear_import_customer(self):self.import_customer_id=None;self.import_customer.setText('Import customer: unassigned (optional)')
    def rebind(self):
        from app.services.orders import OrderStore
        from app.services.print_sessions import PrintSessionStore
        self.customers=CustomerStore(self.w.db);self.orders=OrderStore(self.w.db)
        self.customer_page.store=self.customers;self.order_page.store=self.orders;self.multi.store=PrintSessionStore(self.w.db);self.library.gallery.tray=self.w.tray
        self.library.gallery.label_lookup=self.customers.names_for_photo
        self.clear_import_customer();self.refresh()
    def choose_import_customer(self):
        d=CustomerPicker(self.customers,self.w)
        if d.exec():self.import_customer_id=d.selected_id;self.import_customer.setText('Import customer: '+self.customers.get(d.selected_id)['name']);self.refresh()
    def make_dashboard(self):
        page=QWidget();outer=QVBoxLayout(page);title=QLabel('Your studio workspace');title.setObjectName('title');outer.addWidget(title)
        outer.addWidget(self.w.hardware.panel)
        outer.addWidget(QLabel('Prepare photographs, compose portraits and keep customer work together. Everything stays on this PC.'))
        grid=QGridLayout();grid.setSpacing(16);outer.addLayout(grid)
        modules=[('Cropper','Separate scans and camera photos',self.w.open_cropper),('Portrait Maker','One subject, exact-size prints',lambda:self.w.start_workflow('portrait')),('Joint Photo Maker','Combined or separate subjects',lambda:self.w.start_workflow('joint')),('Customers','Search name or mobile',lambda:self.show(self.customer_page)),('Photo Library','Browse and select numbered photos',lambda:self.show(self.library)),('Print Recipes','Regional profiles and print defaults',self.w.profiles_dialog),('Settings & Backup','Preferences, offline models and safe backup',self.w.settings_dialog)]
        modules.insert(3,('Multi Photo Print','Many compositions, one exact-size PDF',lambda:self.show(self.multi)))
        modules.insert(5,('Orders','History, exact-size PDFs and reprints',lambda:self.show(self.order_page)))
        icons=[QStyle.SP_FileDialogContentsView,QStyle.SP_FileIcon,QStyle.SP_FileLinkIcon,QStyle.SP_FileDialogListView,QStyle.SP_DirHomeIcon,QStyle.SP_FileDialogDetailedView,QStyle.SP_DirOpenIcon,QStyle.SP_FileDialogInfoView,QStyle.SP_ComputerIcon]
        for i,(title,detail,fn) in enumerate(modules):
            card=QFrame();card.setObjectName('card');layout=QVBoxLayout(card);layout.setContentsMargins(18,16,18,16)
            heading=QHBoxLayout();icon=QLabel();icon.setPixmap(self.w.style().standardIcon(icons[i]).pixmap(24,24));heading.addWidget(icon)
            label=QLabel(title);label.setStyleSheet('font-size:17px;font-weight:600;');heading.addWidget(label,1);layout.addLayout(heading)
            description=QLabel(detail);description.setWordWrap(True);layout.addWidget(description)
            b=QPushButton('Open '+title.replace('&','&&'));b.clicked.connect(fn);layout.addWidget(b);grid.addWidget(card,i//3,i%3)
        self.recents=QLabel('Quick access');outer.addWidget(self.recents)
        recent_row=QHBoxLayout();self.recent_customers=QComboBox();self.recent_orders=QComboBox();self.recent_jobs=QComboBox();self.frequent_recipes=QComboBox()
        for box in (self.recent_customers,self.recent_orders,self.recent_jobs,self.frequent_recipes):recent_row.addWidget(box,1)
        outer.addLayout(recent_row)
        tools=QPushButton('Studio tools — batch, contact sheets, order QR, receipts, calibration and statistics');tools.clicked.connect(lambda:self.show(self.tools));outer.addWidget(tools);outer.addStretch(1)
        self.recent_customers.activated.connect(self.recent_customer);self.recent_orders.activated.connect(self.recent_order);self.recent_jobs.activated.connect(lambda index:self.open_job(self.recent_jobs.itemData(index)) if index else None);self.frequent_recipes.activated.connect(self.quick_recipe)
        self.refresh();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);return scroll
    def refresh(self):
        customers=self.customers.search(limit=4);jobs=self.w.db.jobs()[:4]
        if hasattr(self,'recent_customers'):
            from app.services.profiles import normalize_profile
            usage=self.w.db.get('recipe_usage',{});recipes=sorted([normalize_profile(p,validate=False) for p in self.w.db.profiles()],key=lambda p:usage.get(p['recipe_id'],0),reverse=True)[:4]
            groups=[(self.recent_customers,'Recent customers',[(c['name'],c['id']) for c in customers]),(self.recent_orders,'Recent orders',[(f'O{o["serial"]:06d} · {o["status"]}',o['id']) for o in self.orders.search()[:4]]),(self.recent_jobs,'Recent jobs',[(name,id) for id,name,date in jobs]),(self.frequent_recipes,'Frequent recipes',[(p['name'],p['name']) for p in recipes])]
            for box,title,values in groups:
                box.blockSignals(True);box.clear();box.addItem(title,None)
                for text,id in values:box.addItem(text,id)
                box.blockSignals(False)
        if hasattr(self.w,'shell'):self.w.shell.refresh_overview()
    def recent_customer(self,index):
        if index:self.customer_page.search.setText('C%06d'%self.customers.get(self.recent_customers.itemData(index))['serial']);self.show(self.customer_page)
    def recent_order(self,index):
        if index:self.order_page.customer_id=None;self.order_page.search.clear();self.order_page.status.setCurrentIndex(0);self.order_page.current_id=self.recent_orders.itemData(index);self.show(self.order_page)
    def quick_recipe(self,index):
        if not index:return
        name=self.frequent_recipes.itemData(index)
        from app.services.profiles import normalize_profile
        recipe=next((normalize_profile(p) for p in self.w.db.profiles() if p['name']==name),None)
        if recipe and self.w.start_workflow('portrait' if recipe['kind']=='Individual' else 'joint'):
            self.w.profile_picker.setCurrentText(name);self.w.apply_selected_profile()
    def link_job(self,job):
        ids={id for p in job.photos for id in p.provenance.get('library_ids',[])}
        with self.w.db.conn:
            for id in ids:
                self.w.db.conn.execute('INSERT OR IGNORE INTO customer_job_links SELECT customer_id,? FROM customer_photo_links WHERE photo_id=?',(job.id,id))
    def show(self,page):
        if self.w.busy or not self.w.save_before_leave():return
        self.w.timer.stop()
        if page is self.library:page.gallery.refresh()
        if page in (self.customer_page,self.order_page):page.refresh()
        if page is self.tools:page.refresh()
        self.w.stack.setCurrentWidget(page)
        if page is self.multi:page.refresh()
    def customer_photos(self,id):self.library.customer_id=id;self.show(self.library)
    def customer_orders(self,id):self.order_page.customer_id=id;self.order_page.search.clear();self.show(self.order_page)
    @recoverable_record
    def open_job(self,id):
        if not self.w.save_before_leave():return
        job=checked_document(self.w.db.load_job(id))
        row=self.w.db.conn.execute('SELECT id FROM print_sessions WHERE job_id=?',(job.id,)).fetchone()
        if row or len(job.photos)!=1:
            if row:self.multi.load_session(row[0])
            else:
                import uuid
                self.multi.job=copy.deepcopy(job);self.multi.job.id=uuid.uuid4().hex;self.multi.session_id=None;self.multi.persist()
            self.show(self.multi);return
        self.w.adopt_job(job);self.w.sync_controls();self.w.stack.setCurrentIndex(1)
