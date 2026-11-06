"""Categorized preferences for the active studio; legacy settings remain available."""
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor,QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,
    QScrollArea,QLabel,QLineEdit,QComboBox,QCheckBox,QSpinBox,QDoubleSpinBox,QPushButton,
    QFileDialog,QColorDialog)
from app.core.database import data_root
from app.services.preferences import default_preferences,validate_preferences
from app.services.profiles import normalize_profile
from app.services.imaging import find_background_model
from app.services.storage import backup_data,storage_usage,clear_safe_cache
from app.ui.settings import Settings
from app.ui.profiles import Profiles
from app.ui.print_options import PrintOptions


class StudioSettings(Settings):
    def __init__(self,db,run,notify,theme,profiles_changed=lambda:None,restore=None,references=()):
        QWidget.__init__(self)
        self.db,self.run,self.notify,self.theme=db,run,notify,theme
        self.fields={};self.defaults=default_preferences();self.tabs=QTabWidget();outer=QVBoxLayout(self);outer.addWidget(self.tabs)
        for mode,key in [('portrait','default_profile'),('joint','joint_profile')]:
            name=db.get(key,self.defaults[key]);raw=next((p for p in db.profiles() if p['name']==name),None)
            if raw:
                p=normalize_profile(raw,validate=False)
                for dimension in ('width','height'):self.defaults[mode+'_'+dimension]=p[dimension]
                if mode=='portrait':
                    for field in ('background','quantity','border','border_color','border_mm','layout','rows','columns'):self.defaults[field]=p[field]
        def tab(title):
            content=QWidget();form=QFormLayout(content);form.setContentsMargins(12,12,12,12);form.setSpacing(12)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);self.tabs.addTab(scroll,title);return form
        general=tab('General')
        self.add(general,'default_workflow','Start at',choices=[('Dashboard','dashboard'),('Cropper','cropper'),('Portrait print','portrait'),('Joint photo print','joint')])
        for key,title,kind in [('default_profile','Default portrait profile','Individual'),('joint_profile','Default joint profile','Joint')]:
            options=[('Custom dimensions','')]+[(p['name'],p['name']) for p in db.profiles() if normalize_profile(p,validate=False)['kind']==kind]
            self.add(general,key,title,choices=options)
        self.add(general,'output','Default save folder');button=QPushButton('Choose save folder…');button.clicked.connect(self.choose_folder);general.addRow(button)
        self.add(general,'show_guides','Show positioning guides')
        general.addRow(QLabel('Preferences apply to new jobs. Existing jobs keep their saved settings.'))
        photo=tab('Photo')
        for key,title in [('portrait_width','Portrait width (mm)'),('portrait_height','Portrait height (mm)'),('joint_width','Joint width (mm)'),('joint_height','Joint height (mm)'),('background','Default background'),('quantity','Default copies'),('border','Enable border'),('border_color','Border color'),('border_mm','Border thickness (mm)')]:self.add(photo,key,title)
        for key,title in [('background','Choose background color'),('border_color','Choose border color')]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,k=key:self.pick_color(k));photo.addRow(button)
        note=QLabel('Saved photo preferences override profile defaults for new jobs. Apply a profile in the editor to use all of that profile’s settings.');note.setWordWrap(True);photo.addRow(note)
        print_form=tab('Print');self.print_options=PrintOptions();self.print_options.load({k:db.get(k,v) for k,v in self.defaults.items()});print_form.addRow(self.print_options)
        self.add(print_form,'dpi','Image render DPI')
        self.printer=QLineEdit(db.get('printer_name','Default printer'));print_form.addRow('Printer name',self.printer)
        self.measured=QDoubleSpinBox();self.measured.setRange(50,150);self.measured.setValue(100);self.measured.setSuffix(' mm');print_form.addRow('Measured 100 mm test square',self.measured)
        button=QPushButton('Save printer calibration');button.clicked.connect(self.calibrate);print_form.addRow(button)
        note=QLabel('Print at Actual Size / 100%. Calibration is stored for manual application in the printer driver; nominal photo PDF dimensions stay exact.');note.setWordWrap(True);print_form.addRow(note)
        self.tabs.addTab(Profiles(db,profiles_changed),'Profiles')
        processing=tab('Processing');self.defaults['model_dir']=str(data_root()/'models');self.add(processing,'model_dir','Local model folder')
        self.add(processing,'processing_quality','Segmentation quality',choices=[('Fast (smaller working image)','fast'),('Balanced','balanced'),('Fine edges (guided matte)','fine')])
        self.add(processing,'automatic_framing','Initial framing',choices=[('Balanced margins','balanced'),('Document frame','document'),('Legacy head and shoulders','auto'),('Fit whole image','fit'),('Fill canvas','fill')])
        try:
            model=find_background_model(db.get('model_dir'));description=f'{model.name} · {model.stat().st_size/1_000_000:.1f} MB · local CPU processing'
        except ValueError:description='No model installed. Install one below before removing backgrounds.'
        note=QLabel(description);note.setWordWrap(True);processing.addRow(note)
        for title,name in [('Install portrait model (~176 MB)','u2net_human_seg'),('Install lightweight model (~5 MB)','u2netp')]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,n=name:self.install(n));processing.addRow(button)
        storage=tab('Storage');root=data_root();label=QLabel(str(root));label.setWordWrap(True);storage.addRow('Application data',label)
        button=QPushButton('Open application-data folder');button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(root))));storage.addRow(button)
        self.usage=QLabel('Click Measure storage to calculate library usage.');storage.addRow(self.usage)
        button=QPushButton('Measure storage');button.clicked.connect(lambda:self.run(lambda:storage_usage(root),lambda value:self.usage.setText(f'Library {value["library"]/1_000_000:.1f} MB · All app data {value["total"]/1_000_000:.1f} MB')));storage.addRow(button)
        self.include_models=QCheckBox('Include downloaded models in backup');storage.addRow(self.include_models)
        button=QPushButton('Back up jobs, library and settings…');button.clicked.connect(self.backup);storage.addRow(button)
        button=QPushButton('Verify and restore a backup…');button.setEnabled(restore is not None);button.clicked.connect(lambda:restore() if restore else None);storage.addRow(button)
        button=QPushButton('Clear old unreferenced cache files');button.clicked.connect(lambda:self.run(lambda:clear_safe_cache(root,references),lambda value:self.notify(f'Removed {value["files"]} old cache files ({value["bytes"]/1_000_000:.1f} MB). Saved-job images were retained.')));storage.addRow(button)
        note=QLabel('Restore verifies checksums and database integrity, remaps asset paths, and retains the current data folder before restarting. Cache cleanup keeps all saved-job references and current edits.');note.setWordWrap(True);storage.addRow(note)
        self.message=QLabel();self.message.setWordWrap(True);outer.addWidget(self.message);button=QPushButton('Save preferences');button.clicked.connect(self.save);outer.addWidget(button)
        for mode,key in [('portrait','default_profile'),('joint','joint_profile')]:
            self.fields[key].currentIndexChanged.connect(lambda index,m=mode,k=key:self.default_profile_changed(m,k))

    def default_profile_changed(self,mode,key):
        raw=next((p for p in self.db.profiles() if p['name']==self.fields[key].currentData()),None)
        if not raw:return
        p=normalize_profile(raw,validate=False)
        for dimension in ('width','height'):self.fields[mode+'_'+dimension].setValue(p[dimension])
        for field in ('background','quantity','border','border_color','border_mm'):
            control=self.fields[field]
            if isinstance(control,QCheckBox):control.setChecked(p[field])
            elif isinstance(control,(QDoubleSpinBox,QSpinBox)):control.setValue(p[field])
            else:control.setText(p[field])
        values=self.print_options.value();values.update({k:p[k] for k in ('layout','rows','columns')});self.print_options.load(values)

    def add(self,form,key,title,choices=None):
        value=self.db.get(key,self.defaults[key])
        if choices:
            control=QComboBox()
            for label,data in choices:control.addItem(label,data)
            control.setCurrentIndex(max(0,control.findData(value)))
        elif isinstance(value,bool):control=QCheckBox();control.setChecked(value)
        elif key in ('quantity','dpi'):
            control=QSpinBox();control.setRange(1 if key=='quantity' else 72,10000 if key=='quantity' else 600);control.setValue(value)
        elif isinstance(value,(float,int)):
            control=QDoubleSpinBox();control.setDecimals(2);control.setRange(0,1000);control.setValue(value)
        else:control=QLineEdit(str(value))
        self.fields[key]=control;form.addRow(title,control)

    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Default save folder',self.fields['output'].text())
        if folder:self.fields['output'].setText(folder)

    def pick_color(self,key):
        color=QColorDialog.getColor(QColor(self.fields[key].text()),self)
        if color.isValid():self.fields[key].setText(color.name())

    def save(self):
        try:
            values={key:control.currentData() if isinstance(control,QComboBox) else control.isChecked() if isinstance(control,QCheckBox) else control.value() if isinstance(control,(QSpinBox,QDoubleSpinBox)) else control.text() for key,control in self.fields.items()}
            values.update(self.print_options.value());validate_preferences(values)
            with self.db.conn:
                import json
                self.db.conn.executemany('INSERT OR REPLACE INTO config VALUES(?,?)',[(k,json.dumps(v)) for k,v in values.items()])
            self.message.setText('Preferences saved. They will apply to new jobs.');self.notify('Studio preferences saved.');self.theme()
        except Exception as e:self.message.setText('Preferences were not saved: '+str(e))

    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,'Back up studio data',str(Path.home()/'Documents'/'StudioPhotoMaker-backup.zip'),'Studio backup (*.zip)')
        if path:
            include=self.include_models.isChecked()
            self.run(lambda:backup_data(data_root(),path,include),lambda saved:self.notify('Verified-manifest backup saved: '+saved))
