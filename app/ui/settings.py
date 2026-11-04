from pathlib import Path
import urllib.request
from PySide6.QtWidgets import QWidget,QFormLayout,QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox,QPushButton,QLabel,QCheckBox,QFileDialog
from app.core.database import data_root

class Settings(QWidget):
    def __init__(self,db,run,notify,theme):
        super().__init__();self.db=db;self.run=run;self.notify=notify;self.theme=theme;self.fields={};form=QFormLayout(self)
        defaults=dict(background='#ADD8E6',default_profile='Studio Portrait',joint_profile='Studio Joint Photo',quantity=4,border=True,border_color='#808080',border_mm=.2,paper='A4',margin=10,gap_x=2,gap_y=3,output=str(Path.home()/'Documents'),theme='Dark',model_dir=str(data_root()/'models'),dpi=300)
        labels=dict(background='Default background',default_profile='Default portrait profile',joint_profile='Default joint profile',quantity='Default copies',border='Default border enabled',border_color='Default border color',border_mm='Default border (mm)',paper='Paper',margin='Page margins (mm)',gap_x='Horizontal gap (mm)',gap_y='Vertical gap (mm)',output='Output directory',theme='Theme',model_dir='Local model directory',dpi='Image render DPI')
        for key,value in defaults.items():
            value=db.get(key,value)
            if key in ('default_profile','joint_profile','theme','paper'):
                w=QComboBox();w.addItems(['Dark','Light'] if key=='theme' else ['A4'] if key=='paper' else [p['name'] for p in db.profiles()]);w.setCurrentText(value)
            elif key=='border':w=QCheckBox();w.setChecked(value)
            elif key in ('quantity','dpi'):
                w=QSpinBox();w.setRange(1 if key=='quantity' else 72,10000 if key=='quantity' else 600);w.setValue(value)
            elif isinstance(value,(int,float)):
                w=QDoubleSpinBox();w.setDecimals(2);w.setRange(0,80);w.setValue(value)
            else:w=QLineEdit(str(value))
            self.fields[key]=w;form.addRow(labels[key],w)
        b=QPushButton('Save preferences');b.clicked.connect(self.save);form.addRow(b)
        b=QPushButton('Install portrait-quality background model (~176 MB, recommended)');b.clicked.connect(lambda:self.install('u2net_human_seg'));form.addRow(b)
        b=QPushButton('Install lightweight fallback model (~5 MB)');b.clicked.connect(lambda:self.install('u2netp'));form.addRow(b)
        form.addRow(QLabel('Photographs stay on this PC. After model installation, editing works offline.'))
        self.printer=QLineEdit(db.get('printer_name','Default printer'));form.addRow('Printer name',self.printer)
        self.measured=QDoubleSpinBox();self.measured.setRange(50,150);self.measured.setValue(100);self.measured.setSuffix(' mm');form.addRow('Measured 100 mm test square',self.measured)
        b=QPushButton('Save printer calibration');b.clicked.connect(self.calibrate);form.addRow(b)
        form.addRow(QLabel('Print PDFs at Actual Size / 100%. Never use Fit to Page.\nCalibration factors are stored per printer; apply them in the printer driver.\nPDF dimensions remain exact. Check your printer’s printable margins.'))
    def save(self):
        from PIL import ImageColor
        try:
            for key in ('background','border_color'):ImageColor.getrgb(self.fields[key].text())
            for key,w in self.fields.items():
                value=w.isChecked() if isinstance(w,QCheckBox) else w.currentText() if isinstance(w,QComboBox) else w.value() if isinstance(w,(QSpinBox,QDoubleSpinBox)) else w.text()
                self.db.set(key,value)
            self.theme();self.notify('Preferences saved.')
        except Exception as e:self.notify(str(e))
    def calibrate(self):
        name=self.printer.text().strip() or 'Default printer';self.db.set('printer_name',name);values=self.db.get('calibrations',{});values[name]=100/self.measured.value();self.db.set('calibrations',values);self.notify(f'Saved {name}: printer driver scale {10000/self.measured.value():.3f}%.')
    def install(self,model_name='u2net_human_seg'):
        folder=Path(self.fields['model_dir'].text())
        def download():
            import hashlib
            folder.mkdir(parents=True,exist_ok=True);target=folder/(model_name+'.onnx');tmp=folder/(model_name+'.download')
            try:
                urllib.request.urlretrieve('https://github.com/danielgatis/rembg/releases/download/v0.0.0/'+model_name+'.onnx',tmp)
                checksum='c09ddc2e0104f800e3e1bb4652583d1f' if model_name=='u2net_human_seg' else '8e83ca70e441ab06c318d82300c84806'
                if hashlib.md5(tmp.read_bytes()).hexdigest()!=checksum:raise ValueError('Model checksum mismatch. Download was not installed.')
                tmp.replace(target)
            finally:
                if tmp.exists():tmp.unlink()
            return str(target)
        self.db.set('model_dir',str(folder));self.run(download,lambda path:self.notify('Local model installed: '+path))
