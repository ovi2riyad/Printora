"""A single navigation shell around the retained studio workspaces."""
from PySide6.QtCore import Qt,QSize,QTimer,QEvent,QRect,Signal
from PySide6.QtGui import QPainter,QPixmap,QColor
from pathlib import Path
import sys
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QListWidget,
    QListWidgetItem,QComboBox,QFrame,QScrollArea,QStyle,QApplication,QToolBar,QToolButton,QMenu)
from app.ui.theme import apply_theme
from app.ui.icons import icon
from app.ui.panels import AdaptivePanel,splitter

class HeroBanner(QFrame):
    def __init__(self):
        super().__init__();self.setObjectName('hero');self.setMinimumHeight(140)
        self.art=QPixmap(str(Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'assets/studio-hero.png'))
    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.art.isNull():
            painter=QPainter(self);painter.setRenderHint(QPainter.SmoothPixmapTransform)
            path=__import__('PySide6.QtGui',fromlist=['QPainterPath']).QPainterPath();path.addRoundedRect(self.rect().adjusted(1,1,-1,-1),12,12);painter.setClipPath(path)
            width=round(self.height()*self.art.width()/self.art.height());painter.drawPixmap(QRect(self.width()-width,1,width,self.height()-2),self.art);painter.end()

class WorkflowCard(QFrame):
    clicked=Signal()
    def __init__(self):
        super().__init__();self.setFocusPolicy(Qt.StrongFocus);self.setCursor(Qt.PointingHandCursor)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.rect().contains(event.position().toPoint()):self.clicked.emit()
        super().mouseReleaseEvent(event)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Space):self.clicked.emit();event.accept();return
        super().keyPressEvent(event)

class WorkspaceScroll(QScrollArea):
    """Size the active page, avoiding QStackedLayout's inactive height-for-width."""
    def __init__(self,stack):
        super().__init__();self.pending=False;self.setWidgetResizable(False);self.setWidget(stack);stack.currentChanged.connect(self.schedule_fit)
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit_workspace)
    def schedule_fit(self,*_):
        if not self.pending:self.pending=True;self.fit_timer.start(0)
    def fit_workspace(self):
        self.pending=False;stack=self.widget();current=stack.currentWidget()
        if current:
            minimum=current.minimumSizeHint().expandedTo(QSize(0,0))
            if stack.minimumSize()!=minimum:stack.setMinimumSize(minimum)
            size=self.viewport().size().expandedTo(minimum)
            if stack.size()!=size:stack.resize(size)
    def resizeEvent(self,event):super().resizeEvent(event);self.schedule_fit()

class StudioShell:
    def __init__(self,w):
        self.w=w;self.expanded=True;self.routes=[]
        layout=w.centralWidget().layout();layout.setContentsMargins(12,10,12,10);layout.setSpacing(8)
        old=layout.takeAt(0).layout()
        while old.count():
            item=old.takeAt(0)
            if item.widget():item.widget().hide()
        top=QHBoxLayout();toggle=QPushButton();toggle.setIcon(icon('menu'));toggle.setAccessibleName('Expand or collapse navigation');toggle.clicked.connect(self.toggle);top.addWidget(toggle)
        logo_icon=QLabel();self.logo_icon=logo_icon;logo_icon.setPixmap(icon('camera','#20c5e6',36).pixmap(36,36));top.addWidget(logo_icon)
        from app.version import VERSION
        brand=QVBoxLayout();brand.setSpacing(0);logo=QLabel('Printora '+VERSION.rsplit('.',1)[0]);logo.setObjectName('brand');brand.addWidget(logo)
        tag=QLabel('Photography & Document Studio');tag.setObjectName('muted');brand.addWidget(tag);top.addLayout(brand)
        self.workspace=QLabel('Dashboard');top.addWidget(self.workspace);top.addStretch()
        self.device_status=QLabel('Devices: not checked');self.device_status.setObjectName('muted');top.addWidget(self.device_status)
        theme=QComboBox();self.theme_picker=theme;theme.addItems(['System','Light','Dark']);theme.setCurrentText(w.db.get('theme','Dark'))
        theme.activated.connect(lambda index:self.set_theme(theme.currentText()));top.addWidget(theme)
        settings=QToolButton();settings.setIcon(icon('settings'));settings.setToolTip('Settings');settings.setAccessibleName('Settings');settings.clicked.connect(self.open_settings);top.addWidget(settings);layout.insertLayout(0,top)
        self.action_toolbar=QToolBar('Import and output');self.action_toolbar.setMovable(False);self.action_toolbar.setIconSize(QSize(22,22));self.action_toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toolbar_actions={}
        def action(key,title,name,fn):
            item=self.action_toolbar.addAction(icon(name),title);item.setToolTip(title);item.triggered.connect(fn);self.toolbar_actions[key]=item
        action('import','Import photos','import',w.import_to_cropper);action('scan','Scan','scan',lambda:w.hardware.open_scan());action('files','Import documents','copy',lambda:self.import_existing());action('library','Library','library',lambda:w.studio.show(w.studio.library))
        spacer=QWidget();spacer.setStyleSheet('background:transparent;');spacer.setSizePolicy(__import__('PySide6.QtWidgets',fromlist=['QSizePolicy']).QSizePolicy.Expanding,__import__('PySide6.QtWidgets',fromlist=['QSizePolicy']).QSizePolicy.Preferred);self.action_toolbar.addWidget(spacer)
        action('save','Save','save',w.save_job);action('image','Export image','export',self.export_image);action('pdf','Save PDF','recipes',self.export_pdf);action('print','Print','print',self.print_active)
        layout.insertWidget(1,self.action_toolbar)
        layout.removeWidget(w.stack);self.navigation=QListWidget();self.navigation.setObjectName('navigation');self.navigation.setMinimumWidth(0);self.navigation.setIconSize(QSize(20,20));self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navigation_panel=AdaptivePanel(self.navigation,w.db,'navigation','Workspaces',navigation=True,default_width=200);self.navigation_panel.mode_changed.connect(lambda mode:self.render_navigation());self.expanded=self.navigation_panel.mode!='icons'
        self.workspace_scroll=WorkspaceScroll(w.stack);self.body_splitter=splitter(self.navigation_panel,self.workspace_scroll);layout.insertWidget(2,self.body_splitter,1)
        from app.ui.hardware import ScanDialog
        if w.hardware.scan_dialog is None:w.hardware.scan_dialog=ScanDialog(w.hardware)
        self.scan=w.hardware.scan_dialog;self.scan.setWindowFlags(Qt.Widget);w.stack.addWidget(self.scan)
        from app.ui.document_studio import DocumentStudio
        self.copy=DocumentStudio(w,'copy');self.nid=DocumentStudio(w,'nid');w.stack.addWidget(self.copy);w.stack.addWidget(self.nid)
        entries=[('Dashboard',lambda:w.home(),w.stack.widget(0)),('Scan Studio',lambda:w.hardware.open_scan(),self.scan),
            ('Quick Copy',lambda:self.open(self.copy),self.copy),('ID Card Print',lambda:self.open(self.nid),self.nid),
            ('Portrait Maker',lambda:w.start_workflow('portrait'),w.stack.widget(1)),('Joint Photo Maker',lambda:w.start_workflow('joint'),w.stack.widget(1)),
            ('Multi Photo Print',lambda:w.studio.show(w.studio.multi),w.studio.multi),('Photo Library',lambda:w.studio.show(w.studio.library),w.studio.library),
            ('Customers',lambda:w.studio.show(w.studio.customer_page),w.studio.customer_page),('Orders & Reprints',lambda:w.studio.show(w.studio.order_page),w.studio.order_page),
            ('Recipes',self.open_recipes,None),('Studio Tools',lambda:w.studio.show(w.studio.tools),w.studio.tools),('Settings',self.open_settings,None)]
        names=['dashboard','scan','copy','card','portrait','joint','multi','library','joint','orders','recipes','tools','settings']
        for (title,fn,page),name in zip(entries,names):
            item=QListWidgetItem(icon(name),title);item.setToolTip(title);item.setSizeHint(QSize(174,35));self.navigation.addItem(item);self.routes.append((title,fn,page))
        self.navigation.itemClicked.connect(self.navigate);self.navigation.itemActivated.connect(self.navigate);w.stack.currentChanged.connect(self.active)
        self.dashboard();self.active();QApplication.styleHints().colorSchemeChanged.connect(w.apply_theme)
        self.resize(w.size().width());self.refresh_icons()
        from app.services.user_folders import KINDS,dialog_folder
        for kind in KINDS:dialog_folder(w.db,kind,w.notify)
    def refresh_icons(self):
        color='#e6edf8' if self.w.property('themeMode')=='Dark' else '#17243b'
        names=['dashboard','scan','copy','card','portrait','joint','multi','library','joint','orders','recipes','tools','settings']
        for i,name in enumerate(names):self.navigation.item(i).setIcon(icon(name,color))
        for key,name in [('import','import'),('scan','scan'),('files','copy'),('library','library'),('save','save'),('image','export'),('pdf','recipes'),('print','print')]:self.toolbar_actions[key].setIcon(icon(name,color))
        for panel in self.w.findChildren(AdaptivePanel):panel.refresh_icons(color)
        for card,name in zip(getattr(self,'action_cards',[]),('scan','copy','card','print')):card.findChild(QLabel,'tileIcon').setPixmap(icon(name,'#ffffff',44).pixmap(44,44))
    def set_theme(self,mode):self.w.db.set('theme',mode);self.w.apply_theme()
    def open_settings(self):
        if not self.w.save_before_leave():return
        if not hasattr(self,'preferences'):
            from app.ui.studio_settings import StudioSettings
            self.preferences=StudioSettings(self.w.db,self.w.run,self.w.notify,self.w.apply_theme,self.w.refresh_profiles,self.w.restore_backup)
            self.w.stack.addWidget(self.preferences);self.routes[-1]=('Settings',self.open_settings,self.preferences)
        self.w.stack.setCurrentWidget(self.preferences)
    def open_recipes(self):
        if not self.w.save_before_leave():return
        if not hasattr(self,'recipes'):
            from app.ui.profiles import Profiles
            self.recipes=Profiles(self.w.db,self.w.refresh_profiles);self.w.stack.addWidget(self.recipes);self.routes[10]=('Recipes',self.open_recipes,self.recipes)
        self.w.stack.setCurrentWidget(self.recipes)
    def toggle(self):
        modes=['large','small','icons'];self.navigation_panel.set_mode(modes[(modes.index(self.navigation_panel.mode)+1)%3])
    def resize(self,width):
        self.device_status.setVisible(width>=1200);self.workspace.setVisible(width>=850);self.logo_icon.setVisible(width>=800);self.action_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly if width<1100 else Qt.ToolButtonTextBesideIcon);self.render_navigation();self.reflow_dashboard(width)
    def render_navigation(self):
        self.expanded=self.navigation_panel.mode!='icons'
        for i,(title,_,_) in enumerate(self.routes):
            item=self.navigation.item(i);item.setText(title if self.expanded else '');item.setSizeHint(QSize(174 if self.expanded else 40,35))
    def navigate(self,item):
        index=self.navigation.row(item)
        if 0<=index<len(self.routes):self.routes[index][1]();self.active()
    def open(self,page):
        if not self.w.save_before_leave():return
        self.w.timer.stop();self.w.stack.setCurrentWidget(page)
    def active(self,*_):
        current=self.w.stack.currentWidget();index=next((i for i,(_,_,page) in enumerate(self.routes) if page is current),0)
        if current is self.w.stack.widget(1) and self.w.mode=='joint':index=5
        if self.w.stack.currentIndex()==2:index=5 if self.w.mode=='joint' else 4
        self.navigation.setCurrentRow(index);self.workspace.setText(self.routes[index][0])
        document=current in (self.copy,self.nid);editor=current in (self.w.stack.widget(1),self.w.stack.widget(2));multi=current is self.w.studio.multi
        for key in ('pdf','image','print','save'):self.toolbar_actions[key].setEnabled(document or editor or multi or (key=='print' and current is self.w.studio.order_page))
        self.toolbar_actions['image'].setEnabled(document or editor)
        self.toolbar_actions['pdf'].setText('Review PDF' if current is self.w.stack.widget(1) else 'Save PDF')
        for key in ('save','image','pdf','print'):
            self.toolbar_actions[key].setVisible(not document and current is not self.scan and not (key=='pdf' and current is self.w.stack.widget(1)))
        hub=self.w.hardware
        self.device_status.setText('Devices not checked' if hub.scanner.currentText()=='Not checked' and hub.printer.currentText()=='Not checked' else 'Scanner '+('detected' if hub.scanners else 'not found')+' · Printer '+('detected' if hub.printers else 'not found'))
    def print_active(self):
        page=self.w.stack.currentWidget()
        if page in (self.copy,self.nid):page.print_job();return
        if page is self.w.studio.multi:self.w.hardware.print_job(page.job);return
        if page in (self.w.stack.widget(1),self.w.stack.widget(2)):
            self.w.hardware.print_job(self.w.job);return
        if page is self.w.studio.order_page:
            if hasattr(page,'print_current'):page.print_current();return
        self.w.notify('Open a prepared composition, print session, document or order before printing.')
    def export_pdf(self):
        page=self.w.stack.currentWidget()
        if page in (self.copy,self.nid):page.export()
        elif page is self.w.studio.multi:page.export()
        elif page is self.w.stack.widget(1):self.w.show_print()
        elif page is self.w.stack.widget(2):self.w.print_pdf()
    def export_image(self):
        page=self.w.stack.currentWidget()
        if page in (self.copy,self.nid):page.export_image()
        elif page in (self.w.stack.widget(1),self.w.stack.widget(2)):self.w.export_image()
    def dashboard(self):
        manager=self.w.studio;scroll=manager.dashboard;old=scroll.takeWidget();page=QWidget();outer=QVBoxLayout(page);outer.setContentsMargins(4,4,4,4);outer.setSpacing(12)
        hero=HeroBanner();self.hero=hero;hero_row=QHBoxLayout(hero);hero_row.setContentsMargins(24,18,18,18)
        text=QVBoxLayout();title=QLabel('Your photography & document studio');title.setObjectName('title');title.setWordWrap(True);text.addWidget(title)
        subtitle=QLabel('Scan, copy, edit, prepare and print — all in one place.');subtitle.setWordWrap(True);subtitle.setObjectName('muted');text.addWidget(subtitle);hero_row.addLayout(text,3)
        hero_row.addStretch(1);text.setSpacing(6);hero_row.setAlignment(text,Qt.AlignVCenter)
        self.dashboard_grid=QGridLayout();self.dashboard_grid.setSpacing(12);outer.addLayout(self.dashboard_grid)
        self.action_grid=QGridLayout();self.action_grid.setSpacing(10);self.action_container=QWidget();self.action_container.setLayout(self.action_grid)
        self.action_cards=[]
        actions=[('Scan Photos','Scan, crop and prepare photos','scan',lambda:self.w.hardware.open_scan(),'blue'),
                 ('Quick Copy','Scan and print copies','copy',lambda:self.open(self.copy),'green'),
                 ('ID Card Print','Prepare front and back together','card',lambda:self.open(self.nid),'purple'),
                 ('Print Existing Files','Import images or PDF pages','print',self.import_existing,'amber')]
        for title,detail,name,fn,accent in actions:
            card=WorkflowCard();card.setObjectName('workflow');card.setProperty('accent',accent);card.setAccessibleName(title);card.setMinimumHeight(148);card.clicked.connect(fn);v=QVBoxLayout(card);v.setContentsMargins(10,12,10,12);v.setSpacing(6)
            emblem=QLabel();emblem.setObjectName('tileIcon');emblem.setAlignment(Qt.AlignCenter);emblem.setPixmap(icon(name,'white',44).pixmap(44,44));v.addWidget(emblem)
            heading=QLabel(title);heading.setObjectName('tileTitle');heading.setWordWrap(True);heading.setAlignment(Qt.AlignCenter);v.addWidget(heading)
            label=QLabel(detail+'  ›');label.setObjectName('tileDetail');label.setWordWrap(True);label.setAlignment(Qt.AlignCenter);v.addWidget(label)
            for child in (emblem,heading,label):child.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.action_cards.append(card)
        self.device_card=QFrame();self.device_card.setObjectName('card');devices=QVBoxLayout(self.device_card)
        heading=QHBoxLayout();label=QLabel('Devices');label.setObjectName('section');heading.addWidget(label,1);refresh=QPushButton('Refresh');refresh.setIcon(icon('refresh'));refresh.clicked.connect(self.w.hardware.refresh);heading.addWidget(refresh);devices.addLayout(heading)
        devices.addWidget(QLabel('Scanner'));devices.addWidget(self.w.hardware.scanner);devices.addSpacing(12);devices.addWidget(QLabel('Printer'));devices.addWidget(self.w.hardware.printer);devices.addSpacing(18)
        status_title=QLabel('System Status');status_title.setObjectName('section');devices.addWidget(status_title);devices.addWidget(self.w.hardware.status);devices.addStretch()
        self.w.hardware.panel.hide();self.w.hardware.panel.deleteLater();self.w.hardware.panel=self.device_card;self.device_card.setMinimumWidth(220)
        self.recent_card=QFrame();self.recent_card.setObjectName('card');recent=QVBoxLayout(self.recent_card);head=QHBoxLayout();recent_title=QLabel('Recent Photos');recent_title.setObjectName('section');head.addWidget(recent_title,1);view=QPushButton('View library');view.clicked.connect(lambda:manager.show(manager.library));head.addWidget(view);recent.addLayout(head)
        self.recent_photos=QListWidget();self.recent_photos.setViewMode(QListWidget.IconMode);self.recent_photos.setIconSize(QSize(66,80));self.recent_photos.setResizeMode(QListWidget.Adjust);self.recent_photos.setMinimumHeight(110);recent.addWidget(self.recent_photos)
        self.activity_card=QFrame();self.activity_card.setObjectName('card');activity=QGridLayout(self.activity_card)
        for i,(label,box) in enumerate([('Recent Jobs',manager.recent_jobs),('Recent Customers',manager.recent_customers),('Quick Reprint',manager.recent_orders),('Print Recipes',manager.frequent_recipes)]):
            activity.addWidget(QLabel(label),i//2*2,i%2);activity.addWidget(box,i//2*2+1,i%2)
        activity.addWidget(QLabel('Reprint from Saved Session'),4,0,1,2);self.sessions=QComboBox();self.sessions.activated.connect(lambda i:self.open_session(self.sessions.itemData(i)) if i else None);activity.addWidget(self.sessions,5,0,1,2)
        self.pending=QLabel();self.pending.setObjectName('muted');outer.addWidget(self.pending);outer.addStretch();scroll.setWidget(page);old.deleteLater();self.refresh_overview();self.reflow_dashboard(self.w.size().width())
    def reflow_dashboard(self,width):
        if not hasattr(self,'dashboard_grid'):return
        columns=4 if width>=1180 else 2
        for i,card in enumerate(self.action_cards):self.action_grid.addWidget(card,i//columns,i%columns)
        if width>=1250:
            self.dashboard_grid.addWidget(self.hero,0,0,1,2);self.dashboard_grid.addWidget(self.device_card,0,2,3,1)
            self.dashboard_grid.addWidget(self.action_container,1,0,1,2)
            self.dashboard_grid.addWidget(self.recent_card,2,0);self.dashboard_grid.addWidget(self.activity_card,2,1)
            self.dashboard_grid.setColumnStretch(0,3);self.dashboard_grid.setColumnStretch(1,2);self.dashboard_grid.setColumnStretch(2,2)
        else:
            self.dashboard_grid.addWidget(self.hero,0,0,1,2);self.dashboard_grid.addWidget(self.action_container,1,0,1,2);self.dashboard_grid.addWidget(self.device_card,2,1)
            self.dashboard_grid.addWidget(self.recent_card,2,0);self.dashboard_grid.addWidget(self.activity_card,3,0,1,2);self.dashboard_grid.setColumnStretch(0,1);self.dashboard_grid.setColumnStretch(1,1);self.dashboard_grid.setColumnStretch(2,0)
    def refresh_overview(self):
        if not hasattr(self,'recent_photos'):return
        from app.ui.canvas import pixmap
        from PySide6.QtGui import QIcon
        self.recent_photos.clear()
        for photo in self.w.tray.query(limit=8):self.recent_photos.addItem(QListWidgetItem(QIcon(pixmap(photo.thumbnail())),f'#{photo.serial:06d}'))
        self.recent_photos.setMaximumHeight(130 if self.recent_photos.count() else 42)
        if not self.recent_photos.count():self.recent_photos.addItem('No prepared photos yet — import or scan to begin.')
        self.sessions.blockSignals(True);self.sessions.clear();self.sessions.addItem('Choose a saved session',None)
        for session in self.w.studio.multi.store.list()[:8]:self.sessions.addItem(session['name'],session['id'])
        self.sessions.blockSignals(False)
        pending=[o for o in self.w.studio.orders.search() if o['status'] not in ('Completed','Cancelled')];self.pending.setText(f'Pending orders: {len(pending)}')
    def import_existing(self):
        self.open(self.copy)
        if self.w.stack.currentWidget() is self.copy:self.copy.import_files()
    def open_session(self,id):
        if self.w.save_before_leave():self.w.studio.multi.load_session(id);self.w.studio.show(self.w.studio.multi)
    def current_document(self):
        page=self.w.stack.currentWidget()
        return page if page in (self.copy,self.nid) else None
    def shutdown(self):
        for page in (self.copy,self.nid):page.shutdown()
    def rebind(self):
        from app.services.documents import DocumentSession
        from app.core.database import data_root
        from app.ui.panels import AdaptivePanel
        for panel in self.w.findChildren(AdaptivePanel):panel.db=self.w.db
        self.w.cropper.settings_db=self.w.db
        for page in (self.copy,self.nid):
            if not page.session.root.exists():page.session=DocumentSession(data_root(),page.kind);page.dirty=False;page.refresh()
        from app.ui.profiles import Profiles
        if hasattr(self,'preferences'):
            self.preferences.db=self.w.db
            for widget in self.preferences.findChildren(Profiles):widget.db=self.w.db;widget.refresh()
        if hasattr(self,'recipes'):self.recipes.db=self.w.db;self.recipes.refresh()
