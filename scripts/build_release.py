"""Build a complete application payload and its client-facing Setup EXE."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from app.version import VERSION
from scripts.setup_installer import ROOT,install_compiler


def make_icon(path):
    from PySide6.QtCore import QByteArray,Qt
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PIL import Image
    source=ROOT/'assets/printora.svg'
    image=QImage(256,256,QImage.Format_RGBA8888);image.fill(Qt.transparent)
    painter=QPainter(image);QSvgRenderer(QByteArray(source.read_bytes())).render(painter);painter.end()
    raw=image.constBits();icon=Image.frombytes('RGBA',(256,256),bytes(raw), 'raw','RGBA',image.bytesPerLine())
    icon.save(path,format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])


def prepare_payload(payload):
    payload=Path(payload).resolve()
    required=[payload/'StudioPhotoMaker.exe',payload/'_internal/models/u2net_human_seg.onnx']
    if not all(p.is_file() for p in required):raise ValueError('The complete application and bundled portrait model are required before building Setup.')
    for name in ('README.md','CREDITS.md','THIRD_PARTY.md','LICENSE'):
        shutil.copy2(ROOT/name,payload/name)
    shutil.copytree(ROOT/'docs',payload/'docs',dirs_exist_ok=True)
    (payload/'assets').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'assets/creator-card.svg',payload/'assets/creator-card.svg')
    shutil.copytree(ROOT/'licenses',payload/'licenses',dirs_exist_ok=True)
    copy_dependency_notices(payload/'licenses/packages')
    make_icon(payload/'Printora.ico')
    return payload


def copy_dependency_notices(destination):
    """Retain wheel-supplied notices and exact metadata beside the application."""
    packages=('PySide6-Essentials','PySide6-PDF','shiboken6','Pillow','opencv-python-headless',
        'reportlab','onnxruntime','numpy','flatbuffers','protobuf','packaging','charset-normalizer')
    for name in packages:
        dist=distribution(name)
        target=destination/name.lower().replace('-','_')
        target.mkdir(parents=True,exist_ok=True)
        (target/'METADATA').write_text(dist.read_text('METADATA') or '',encoding='utf-8')
        for item in dist.files or ():
            path=Path(str(item))
            if path.is_absolute() or '..' in path.parts:continue
            if not ('licenses' in path.parts or path.name.lower().startswith(('license','copying','notice','copyright','authors'))):continue
            source=Path(dist.locate_file(item))
            if not source.is_file():continue
            output=target/path
            output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,output)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():raise ValueError('Python runtime LICENSE.txt is required for redistribution.')
    (destination/'Python').mkdir(exist_ok=True)
    shutil.copy2(python_license,destination/'Python/LICENSE.txt')


def compile_installer(payload,output=None,test_root=None):
    payload=prepare_payload(payload);compiler=install_compiler();output=Path(output or ROOT/'dist/installers').resolve();output.mkdir(parents=True,exist_ok=True)
    args=[str(compiler),f'/DPayload={payload}',f'/DProductVersion={VERSION}',f'/DReleaseOutput={output}']
    if test_root:
        target=Path(test_root).resolve()
        if not target.is_relative_to(ROOT/'.tools'):raise ValueError('Installer testing must stay inside .tools.')
        args.append(f'/DTestRoot={target}')
    args.append(str(ROOT/'installer/Printora.iss'))
    subprocess.run(args,check=True,cwd=ROOT)
    return output/(f'Printora-{VERSION}-'+('InstallerTest.exe' if test_root else 'Setup.exe'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-app',action='store_true');parser.add_argument('--portable-only',action='store_true');parser.add_argument('--payload',default=str(ROOT/'dist/candidate/StudioPhotoMaker'));parser.add_argument('--test-root');parser.add_argument('--output');args=parser.parse_args()
    if not args.skip_app:
        icon=ROOT/'.tools/Printora.ico';icon.parent.mkdir(exist_ok=True);make_icon(icon)
        payload=Path(args.payload).resolve()
        if payload.name!='StudioPhotoMaker':raise ValueError('The payload folder must end in StudioPhotoMaker (PyInstaller onedir name).')
        subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--distpath',str(payload.parent),'--workpath',str(ROOT/'build'/payload.parent.name),'StudioPhotoMaker.spec'],check=True,cwd=ROOT)
    payload=prepare_payload(args.payload)
    if not args.portable_only:
        installer=compile_installer(payload,args.output,args.test_root)
        print('\nCLIENT INSTALLER:',installer,flush=True)
        print('Double-click Setup to install Printora and its bundled dependencies. New installs default to C:\\Printora.',flush=True)
    print('Developer portable folder (keep every file):',payload,flush=True)


if __name__=='__main__':main()
