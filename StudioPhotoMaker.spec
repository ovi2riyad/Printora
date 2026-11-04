from PyInstaller.utils.hooks import collect_all, collect_data_files
from pathlib import Path
import os
datas=[]
binaries=[]
hiddenimports=[]
for package in ('onnxruntime',):
    d,b,h=collect_all(package)
    datas+=d; binaries+=b; hiddenimports+=h
datas+=collect_data_files('cv2')
portrait_model=Path(os.environ.get('LOCALAPPDATA',''))/'StudioPhotoMaker'/'models'/'u2net_human_seg.onnx'
if portrait_model.is_file():datas.append((str(portrait_model),'models'))
a=Analysis(['main.py'],pathex=['.'],binaries=binaries,datas=datas,hiddenimports=hiddenimports,excludes=['tkinter','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','IPython','matplotlib','rembg','pymatting','numba','scipy','skimage'])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='StudioPhotoMaker',console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='StudioPhotoMaker')
