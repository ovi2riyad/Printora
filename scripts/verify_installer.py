"""Exercise the same installer in a compiler-only isolated, non-admin location."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import winreg
from scripts.build_release import compile_installer,ROOT


def run(args,env=None,timeout=240):
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    result=subprocess.run([str(a) for a in args],cwd=ROOT,env=env,timeout=timeout,startupinfo=startup)
    if result.returncode:raise RuntimeError(f'Process exited {result.returncode}: {args[0]}')


def registration(target):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as root:
        for index in range(winreg.QueryInfoKey(root)[0]):
            name=winreg.EnumKey(root,index)
            if '4F077504-7244-4BEB-B290-FE8758932B47' not in name or 'InstallerTest' not in name:continue
            with winreg.OpenKey(root,name) as key:
                if Path(winreg.QueryValueEx(key,'InstallLocation')[0]).resolve()==target:
                    return {'key':name,'name':winreg.QueryValueEx(key,'DisplayName')[0],'version':winreg.QueryValueEx(key,'DisplayVersion')[0]}
    return None


def main():
    p=argparse.ArgumentParser();p.add_argument('--payload',required=True);p.add_argument('--root',required=True);args=p.parse_args()
    root=Path(args.root).resolve()
    if not root.is_relative_to(ROOT/'.tools') or root.exists():raise ValueError('Use a fresh test directory under .tools.')
    root.mkdir(parents=True);app=root/'Application';started=time.monotonic();checks=[];result={};environment=dict(os.environ)
    environment['LOCALAPPDATA']=str(root/'UserData');environment['QT_QPA_PLATFORM']='offscreen';environment['QT_QPA_FONTDIR']='C:/Windows/Fonts';environment.pop('STUDIO_VERIFY_MODEL_DIR',None)
    try:
        installer=compile_installer(args.payload,ROOT/'dist/installer-tests',root)
        flags=['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-']
        run([installer,*flags,f'/LOG={root / "install.log"}']);assert (app/'Printora.exe').is_file() and (app/'_internal/models/u2net_human_seg.onnx').is_file()
        entry=registration(app);assert entry and entry['name'].startswith('Printora Installer Test'),repr(entry);checks.append('Installed files, bundled model and Windows Installed Apps entry')
        shortcut_script="$w=New-Object -ComObject WScript.Shell; $paths=@((Join-Path $env:PRINTORA_TEST_ROOT 'Desktop\\Printora.lnk'),(Join-Path $env:PRINTORA_TEST_ROOT 'StartMenu\\Printora\\Printora.lnk')); foreach($p in $paths){if(!(Test-Path -LiteralPath $p)){throw 'Missing shortcut'}; $s=$w.CreateShortcut($p); if($s.TargetPath -ne (Join-Path $env:PRINTORA_TEST_ROOT 'Application\\Printora.exe')){throw 'Wrong shortcut target'}; if($s.WorkingDirectory -ne (Join-Path $env:PRINTORA_TEST_ROOT 'Application')){throw 'Wrong working directory'}}"
        shortcut_env=dict(environment,PRINTORA_TEST_ROOT=str(root));run(['powershell','-NoProfile','-NonInteractive','-Command',shortcut_script],shortcut_env);checks.append('Desktop and Start menu shortcut targets and working directories')
        user=root/'UserData/StudioPhotoMaker';user.mkdir(parents=True,exist_ok=True);sentinel=user/'preserve-me.txt';sentinel.write_text('Existing customer data must survive upgrade and uninstall.');unknown=app/'customer-created.txt';unknown.write_text('Unknown file: never remove with wildcard uninstall.')
        run([installer,*flags,f'/LOG={root / "upgrade.log"}']);assert sentinel.is_file() and unknown.is_file() and registration(app)['key']==entry['key'];checks.append('Upgrade reuses app registration and preserves user/unknown files')
        run([app/'Printora.exe','--smoke-test',root/'installed-dashboard.png'],environment);assert (root/'installed-dashboard.png').is_file();checks.append('Renamed installed EXE launches without Python')
        run([app/'Printora.exe','--verify-studio',ROOT/'Demo',root/'workflow'],environment,timeout=300)
        workflow=json.loads((root/'workflow/result.json').read_text());assert workflow['passed'] and workflow['total_saved']==68
        checks.append(f'Installed bundled-only full acceptance: {len(workflow["checks"])} checks, 68 photos')
        result=dict(passed=True,checks=checks,workflow_seconds=workflow['seconds'],registration=entry)
    except Exception as e:
        import traceback
        result=dict(passed=False,checks=checks,error=repr(e),traceback=traceback.format_exc())
    finally:
        uninstaller=app/'unins000.exe'
        if uninstaller.exists():
            try:
                run([uninstaller,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={root / "uninstall.log"}'])
                # Inno may use a detached cleanup helper after its primary process exits.
                for _ in range(100):
                    if not (app/'Printora.exe').exists() and not registration(app):break
                    time.sleep(.1)
                assert not (app/'Printora.exe').exists() and registration(app) is None
                assert not (root/'Desktop/Printora.lnk').exists() and not (root/'StartMenu/Printora/Printora.lnk').exists()
                if 'sentinel' in locals():
                    assert sentinel.is_file() and unknown.is_file()
                    checks.append('Uninstall removes app/shortcuts/registration and retains user data and unknown files')
            except Exception as e:result.update(passed=False,uninstall_error=repr(e))
        result['seconds']=round(time.monotonic()-started,2);(root/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    return 0 if result.get('passed') else 1


if __name__=='__main__':raise SystemExit(main())
