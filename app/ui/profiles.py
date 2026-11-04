import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,QPushButton,QDialog,QDialogButtonBox,QFormLayout,QDoubleSpinBox,QComboBox,QMessageBox,QFileDialog,QCheckBox
from app.core.database import starter_profiles

class ProfileDialog(QDialog):
    def __init__(self,p,parent=None):
        super().__init__(parent);self.setWindowTitle('Photo size profile');self.p=dict(p);self.fields={};form=QFormLayout(self)
        for key,label in [('name','Name'),('country','Country'),('document_type','Document type'),('width','Width (mm)'),('height','Height (mm)'),('orientation','Orientation'),('background','Background (#hex)'),('border','Border enabled'),('border_color','Border color'),('border_mm','Border (mm)'),('notes','Notes'),('url','Official source URL'),('verification','Verification')]:
            if key in ('width','height','border_mm'):
                w=QDoubleSpinBox();w.setRange(0 if key=='border_mm' else 1,1000);w.setDecimals(2);w.setValue(float(p.get(key,0.2)))
            elif key=='border':w=QCheckBox();w.setChecked(p.get(key,True))
            else:w=QLineEdit(str(p.get(key,'')))
            self.fields[key]=w;form.addRow(label,w)
        b=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);b.accepted.connect(self.accept);b.rejected.connect(self.reject);form.addRow(b);self.resize(580,580)
    def value(self):
        return {k:w.value() if isinstance(w,QDoubleSpinBox) else w.isChecked() if isinstance(w,QCheckBox) else w.text() for k,w in self.fields.items()}

class Profiles(QWidget):
    def __init__(self,db,changed):
        super().__init__();self.db=db;self.changed=changed;lay=QVBoxLayout(self)
        self.search=QLineEdit();self.search.setPlaceholderText('Search profiles, countries, or document types');self.search.textChanged.connect(self.refresh);lay.addWidget(self.search)
        self.country=QComboBox();self.country.addItem('All countries');self.country.addItems(sorted({p['country'] for p in db.profiles() if p.get('country')}));self.country.currentTextChanged.connect(self.refresh);lay.addWidget(self.country)
        self.list=QListWidget();self.list.itemDoubleClicked.connect(lambda _:self.edit());lay.addWidget(self.list)
        row=QHBoxLayout();lay.addLayout(row)
        for label,fn in [('Add',self.add),('Edit',self.edit),('Duplicate',self.duplicate),('Delete',self.delete),('Set portrait default',self.default),('Import JSON',self.import_json),('Export JSON',self.export_json)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.refresh()
    def refresh(self,*_):
        self.list.clear();self.rows=[]
        for p in self.db.profiles():
            if self.search.text().lower() not in json.dumps(p).lower():continue
            if self.country.currentText() not in ('All countries',p.get('country','')):continue
            self.rows.append(p);self.list.addItem(f"{p['name']}   ·   {p['width']} × {p['height']} mm   ·   {p.get('verification','Requires verification')}")
    def selected(self):
        i=self.list.currentRow();return self.rows[i] if i>=0 else None
    def dialog(self,p):
        d=ProfileDialog(p,self)
        if d.exec():
            try:
                value=d.value()
                from PIL import ImageColor
                ImageColor.getrgb(value['background']);ImageColor.getrgb(value['border_color'])
                self.db.save_profile(value);self.refresh();self.changed()
            except Exception as e:QMessageBox.warning(self,'Invalid profile',str(e))
    def add(self):
        p=starter_profiles()[0];p['name']='New custom profile';p['verification']='Custom — verify requirements';self.dialog(p)
    def edit(self):
        if self.selected():self.dialog(self.selected())
    def duplicate(self):
        if self.selected():
            p=dict(self.selected());p['name']+=' copy';self.dialog(p)
    def delete(self):
        if self.selected():self.db.delete_profile(self.selected()['name']);self.refresh();self.changed()
    def default(self):
        if self.selected():self.db.set('default_profile',self.selected()['name']);self.changed()
    def import_json(self):
        path,_=QFileDialog.getOpenFileName(self,'Import profiles','','JSON (*.json)')
        if path:
            try:
                with open(path,encoding='utf-8') as f:rows=json.load(f)
                if not isinstance(rows,list):raise ValueError('Expected a JSON array of profiles.')
                for p in rows:
                    if not isinstance(p,dict):raise ValueError('Each profile must be an object.')
                    if not p.get('name') or not 0<float(p['width'])<=1000 or not 0<float(p['height'])<=1000:raise ValueError('Invalid profile dimensions or name.')
                for p in rows:self.db.save_profile(p)
                self.refresh();self.changed()
            except Exception as e:QMessageBox.warning(self,'Import failed',str(e))
    def export_json(self):
        path,_=QFileDialog.getSaveFileName(self,'Export profiles','profiles.json','JSON (*.json)')
        if path:
            with open(path,'w',encoding='utf-8') as f:json.dump(self.db.profiles(),f,indent=2)
