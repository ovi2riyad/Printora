"""Build the portable application and a normal all-users Windows installer."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
    for name in ('README.md','PROJECT_INFO.md','VALIDATION.md','TODO.md','THIRD_PARTY.md','GITHUB.md','PHASE_REPORTS_3_0.md'):
        shutil.copy2(ROOT/name,payload/name)
    make_icon(payload/'Printora.ico')
    return payload


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
        subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--distpath','dist/candidate','--workpath','build/candidate','StudioPhotoMaker.spec'],check=True,cwd=ROOT)
    payload=prepare_payload(args.payload)
    if not args.portable_only:print('Installer ready:',compile_installer(payload,args.output,args.test_root))
    print('Portable application:',payload)


if __name__=='__main__':main()
