"""Install a checksum-pinned official Inno compiler in the ignored tools folder."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
SHA256='8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0'


def find_compiler():
    candidates=[os.environ.get('PRINTORA_ISCC',''),ROOT/'.tools/inno/ISCC.exe',shutil.which('ISCC.exe') or '']
    for base in (os.environ.get('ProgramFiles',''),os.environ.get('ProgramFiles(x86)','')):
        for version in (7,6):candidates.append(Path(base)/f'Inno Setup {version}'/'ISCC.exe')
    return next((Path(p).resolve() for p in candidates if p and Path(p).is_file()),None)


def install_compiler():
    compiler=find_compiler()
    if compiler:return compiler
    if os.name!='nt':raise RuntimeError('Windows is required to build the installer.')
    folder=ROOT/'.tools/inno-download';folder.mkdir(parents=True,exist_ok=True)
    source=folder/'innosetup-7.1.1-x64.exe'
    if not source.exists():
        print('Downloading the official Inno Setup build tool (one-time developer setup)...',flush=True)
        temporary=source.with_suffix('.download')
        with urllib.request.urlopen(URL,timeout=90) as incoming,temporary.open('wb') as output:shutil.copyfileobj(incoming,output)
        temporary.replace(source)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA256:raise RuntimeError('Compiler checksum mismatch. Do not run this download; obtain the official matching build tool.')
    target=ROOT/'.tools/inno'
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    subprocess.run([str(source),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/CURRENTUSER','/NOICONS',f'/DIR={target}'],check=True,startupinfo=startup)
    compiler=find_compiler()
    if not compiler:raise RuntimeError('Inno compiler not found. Install Inno Setup, or set PRINTORA_ISCC to ISCC.exe.')
    return compiler


if __name__=='__main__':print(install_compiler())
