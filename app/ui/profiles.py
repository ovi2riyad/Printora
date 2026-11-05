import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,QPushButton,QDialog,QDialogButtonBox,QFormLayout,QDoubleSpinBox,QComboBox,QMessageBox,QFileDialog,QCheckBox,QSpinBox,QLabel,QColorDialog,QScrollArea
from PySide6.QtGui import QColor
from app.core.database import starter_profiles
from app.services.profiles import normalize_profile,REGIONS,LAYOUTS

class ProfileDialog(QDialog):
    def __init__(self,p,parent=None):
        super().__init__(parent);self.setWindowTitle('Photo size profile');self.p=dict(p);self.fields={};outer=QVBoxLayout(self);content=QWidget();form=QFormLayout(content);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);outer.addWidget(scroll,1)
        p=normalize_profile(p,validate=False)
        for key,label in [('name','Name'),('country','Country / region'),('kind','Photo category'),('document_type','Usage / document label'),('width','Width (mm)'),('height','Height (mm)'),('quantity','Default copies'),('background','Background'),('border','Border enabled'),('border_color','Border color'),('border_mm','Border (mm)'),('layout','Default print layout'),('columns','Custom columns'),('rows','Custom rows'),('notes','Notes'),('url','Reference URL'),('verification','Verification')]:
            if key in ('width','height','border_mm'):
                w=QDoubleSpinBox();w.setRange(0 if key=='border_mm' else 1,1000);w.setDecimals(2);w.setValue(float(p.get(key,0.2)))
            elif key in ('quantity','columns','rows'):
                w=QSpinBox();w.setRange(1,10000 if key=='quantity' else 100);w.setValue(p[key])
            elif key in ('country','kind','layout'):
                w=QComboBox()
                if key=='layout':
                    for value,text in LAYOUTS.items():w.addItem(text,value)
                    w.setCurrentIndex(max(0,w.findData(p[key])))
                else:w.setEditable(key=='country');w.addItems(REGIONS if key=='country' else ['Individual','Joint']);w.setCurrentText(p[key])
            elif key=='border':w=QCheckBox();w.setChecked(p.get(key,True))
            else:w=QLineEdit(str(p.get(key,'')))
            self.fields[key]=w;form.addRow(label,w)
        row=QHBoxLayout()
        for key,title in [('background','Pick background'),('border_color','Pick border color')]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,k=key:self.pick_color(k));row.addWidget(button)
        form.addRow(row);self.error=QLabel('Orientation follows dimensions. Presets do not guarantee document compliance.');self.error.setWordWrap(True);outer.addWidget(self.error)
        b=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);b.accepted.connect(self.accept);b.rejected.connect(self.reject);outer.addWidget(b);self.resize(610,700)
    def pick_color(self,key):
        color=QColorDialog.getColor(QColor(self.fields[key].text()),self)
        if color.isValid():self.fields[key].setText(color.name())
    def value(self):
        return normalize_profile({k:w.value() if isinstance(w,(QDoubleSpinBox,QSpinBox)) else w.isChecked() if isinstance(w,QCheckBox) else (w.currentData() if k=='layout' else w.currentText()) if isinstance(w,QComboBox) else w.text() for k,w in self.fields.items()})
    def accept(self):
        try:self.value()
        except (ValueError,TypeError) as e:self.error.setText(str(e));return
        super().accept()

class Profiles(QWidget):
    def __init__(self,db,changed):
        super().__init__();self.db=db;self.changed=changed;lay=QVBoxLayout(self)
        self.search=QLineEdit();self.search.setPlaceholderText('Search profiles, countries, or document types');self.search.textChanged.connect(self.refresh);lay.addWidget(self.search)
        filters=QHBoxLayout();self.country=QComboBox();self.country.addItem('All countries');self.country.addItems(sorted(set(REGIONS)|{p['country'] for p in db.profiles() if p.get('country')}));self.country.currentTextChanged.connect(self.refresh);filters.addWidget(self.country);self.kind=QComboBox();self.kind.addItems(['All photo categories','Individual','Joint']);self.kind.currentTextChanged.connect(self.refresh);filters.addWidget(self.kind);lay.addLayout(filters)
        info=QLabel('Editable studio presets. Verify current authority rules. Selecting a profile preserves image layers and edits.');info.setWordWrap(True);lay.addWidget(info)
        self.list=QListWidget();self.list.itemDoubleClicked.connect(lambda _:self.edit());lay.addWidget(self.list)
        row=QHBoxLayout();lay.addLayout(row)
        for label,fn in [('Add',self.add),('Edit',self.edit),('Duplicate',self.duplicate),('Delete',self.delete),('Set as default',self.default)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        row=QHBoxLayout();lay.addLayout(row)
        for label,fn in [('Restore missing starters',self.restore),('Import JSON',self.import_json),('Export JSON',self.export_json)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.hint=QLabel();lay.addWidget(self.hint)
        self.refresh()
    def refresh(self,*_):
        self.list.clear();self.rows=[]
        for p in self.db.profiles():
            p=normalize_profile(p,validate=False)
            if self.search.text().lower() not in json.dumps(p).lower():continue
            if self.country.currentText() not in ('All countries',p.get('country','')):continue
            if self.kind.currentText() not in ('All photo categories',p['kind']):continue
            self.rows.append(p);self.list.addItem(f"{p['name']}   ·   {p['width']} × {p['height']} mm   ·   {p.get('verification','Requires verification')}")
    def selected(self):
        i=self.list.currentRow();return self.rows[i] if i>=0 else None
    def dialog(self,p,old_name=None):
        d=ProfileDialog(p,self)
        if d.exec():
            try:
                value=d.value()
                from PIL import ImageColor
                ImageColor.getrgb(value['background']);ImageColor.getrgb(value['border_color'])
                if old_name:self.db.rename_profile(old_name,value)
                else:
                    if any(x['name']==value['name'] for x in self.db.profiles()):raise ValueError('Choose a unique profile name.')
                    self.db.save_profile(value)
                self.refresh();self.changed()
            except Exception as e:QMessageBox.warning(self,'Invalid profile',str(e))
    def add(self):
        p=starter_profiles()[0];p['name']='New custom profile';p['country']='Custom';p['verification']='Custom — verify requirements';self.dialog(p)
    def edit(self):
        if self.selected():self.dialog(self.selected(),self.selected()['name'])
    def duplicate(self):
        if self.selected():
            p=dict(self.selected());p['name']+=' copy';self.dialog(p)
    def delete(self):
        if self.selected():self.db.delete_profile(self.selected()['name']);self.refresh();self.changed()
    def default(self):
        if self.selected():
            p=self.selected();self.db.set('joint_profile' if p['kind']=='Joint' else 'default_profile',p['name'])
            prefix='joint' if p['kind']=='Joint' else 'portrait'
            for key in ('width','height'):self.db.set(prefix+'_'+key,p[key])
            self.hint.setText(p['name']+' is the default for '+p['kind'].lower()+' photos.');self.changed()
    def restore(self):self.db.restore_profiles();self.refresh();self.changed();self.hint.setText('Missing starters restored; customized profiles kept.')
    def import_json(self):
        path,_=QFileDialog.getOpenFileName(self,'Import profiles','','JSON (*.json)')
        if path:
            try:
                with open(path,encoding='utf-8') as f:rows=json.load(f)
                if not isinstance(rows,list):raise ValueError('Expected a JSON array of profiles.')
                for p in rows:
                    if not isinstance(p,dict):raise ValueError('Each profile must be an object.')
                    if not p.get('name') or not 0<float(p['width'])<=1000 or not 0<float(p['height'])<=1000:raise ValueError('Invalid profile dimensions or name.')
                rows=[normalize_profile(p) for p in rows]
                with self.db.conn:
                    for p in rows:self.db.conn.execute('INSERT OR REPLACE INTO profiles VALUES(?,?)',(p['name'],json.dumps(p)))
                self.refresh();self.changed()
            except Exception as e:QMessageBox.warning(self,'Import failed',str(e))
    def export_json(self):
        path,_=QFileDialog.getSaveFileName(self,'Export profiles','profiles.json','JSON (*.json)')
        if path:
            with open(path,'w',encoding='utf-8') as f:json.dump(self.db.profiles(),f,indent=2)
