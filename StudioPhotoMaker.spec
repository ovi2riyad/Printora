from PyInstaller.utils.hooks import collect_all, collect_data_files
from pathlib import Path
import os
from scripts.build_release import make_icon
datas=[]
binaries=[]
hiddenimports=[]
for package in ('onnxruntime',):
    d,b,h=collect_all(package)
    datas+=d; binaries+=b; hiddenimports+=h
datas+=collect_data_files('cv2')
icon=Path('.tools/Printora.ico');icon.parent.mkdir(exist_ok=True);make_icon(icon)
datas.append((str(icon),'assets'))
portrait_model=Path(os.environ.get('LOCALAPPDATA',''))/'StudioPhotoMaker'/'models'/'u2net_human_seg.onnx'
if not portrait_model.is_file():raise SystemExit('Portrait model missing. Install it with python -m scripts.install_model before building the offline release.')
datas.append((str(portrait_model),'models'))
a=Analysis(['main.py'],pathex=['.'],binaries=binaries,datas=datas,hiddenimports=hiddenimports,excludes=['tkinter','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','IPython','matplotlib','rembg','pymatting','numba','scipy','skimage'])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='StudioPhotoMaker',console=False,icon=str(icon))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='StudioPhotoMaker')
