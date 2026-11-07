"""Fake device transfers execute the real adapter protocol; no real device calls."""
import os,json,subprocess,time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox
from app.services.hardware import inspect_scans

@pytest.fixture
def app():return QApplication.instance() or QApplication([])

@pytest.fixture
def window(app,tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    from app.ui.studio_window import StudioWindow
    w=StudioWindow();w.show();app.processEvents();yield w
    w.pool.waitForDone();app.processEvents();w.hardware.shutdown();w.shell.copy.dirty=False;w.shell.nid.dirty=False;w.dirty=False;w.timer.stop();w.invalidate_autosave();w.close();app.processEvents()

def wait(w):
    deadline=time.monotonic()+20
    while w.busy and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
    assert not w.busy

@pytest.mark.parametrize('status,warning,expected',[('Ready',False,1),('Ready',True,0),('Offline',False,0),('Queue available; physical readiness unverified',False,0)])
def test_automatic_copy_requires_known_ready_and_submits_once(window,tmp_path,monkeypatch,status,warning,expected):
    from app.services.documents import DocumentSession
    from app.services.pdf import export_pdf
    from app.ui.hardware import PrintDialog
    from app.ui.hardware_process import HardwareProcess
    source=tmp_path/'copy.png';Image.new('RGB',(300,400),'white').save(source);session=DocumentSession(tmp_path);session.import_image(source,dpi=300);job=session.job({'copies':4})
    folder=tmp_path/'spool';folder.mkdir();export_pdf(job,folder/'sheet.pdf')
    hub=window.hardware;hub.printers=[dict(id='Fake',name='Fake',status=status,default=True)];hub.printer.clear();hub.printer.addItem('Fake','Fake');calls=[]
    monkeypatch.setattr(HardwareProcess,'start',lambda self,*args:calls.append(args))
    monkeypatch.setattr(QMessageBox,'question',lambda *a:pytest.fail('Automatic copy must not ask a second confirmation'))
    dialog=PrintDialog(hub,job,folder,['Quality needs review'] if warning else []);hub.print_dialog=dialog;dialog.auto_requested=True
    dialog.result({'area':dict(left=0,top=0,right=210,bottom=297)})
    if expected:dialog.print_now(automatic=True)
    requests=[r[1] for r in calls if r[1]['action']=='print'];assert len(requests)==expected
    if expected:assert requests[0]['job']['page_count']==4 and requests[0]['job']['photos'][0]['quantity']==4
    dialog.close();hub.printing=False

def test_auto_after_scan_uses_only_newly_acquired_pages(window,tmp_path,monkeypatch):
    from app.services.documents import DocumentPage
    w=window;copy=w.shell.copy;w.stack.setCurrentWidget(copy);source=tmp_path/'existing.png';Image.new('RGB',(300,400)).save(source);copy.session.import_image(source,dpi=300);copy.refresh();wait(w)
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes);copy.auto_print.setChecked(True);submitted=[]
    monkeypatch.setattr(w.hardware,'print_job',lambda job,auto=False:submitted.append((job,auto)))
    scanner=w.hardware.scan_dialog;monkeypatch.setattr(scanner,'scan_now',lambda:None);copy.scan('Page')
    added=[]
    for i in range(2):
        path=copy.session.root/f'new-{i}.png';Image.new('RGB',(300,400)).save(path);added.append({'original':str(path),'driver':{'dpi':300}})
    scanner.completion_callback(dict(added[0],pages=added,driver={'dpi':300,'acquired':True}));wait(w)
    assert len(submitted)==1 and submitted[0][1] and len(submitted[0][0].photos)==2 and len(copy.session.pages)==3
    assert all('new-' in p.layers[0].source or 'processed-' in p.layers[0].source for p in submitted[0][0].photos)

@pytest.mark.parametrize('started,verified,attempts,expected',[(False,True,0,1),(True,True,0,0),(False,False,0,0),(False,True,1,0)])
def test_actual_hub_fallback_gate(window,tmp_path,monkeypatch,started,verified,attempts,expected):
    hub=window.hardware;dialog=hub.scan_dialog
    hub.scanners=[dict(id='primary',name='Primary',backend='wia'),dict(id='twain32:alternate',name='Alternate',backend='twain32')];dialog.update_devices()
    dialog.folder=tmp_path/'scan';dialog.folder.mkdir();hub.scan_action='scan';hub.scan_request=dict(device='primary',dpi=300,color='color',region=[0,0,210,297]);hub.fallback_attempts=attempts
    hub.w.db.set('scanner_fallbacks',{'primary':'twain32:alternate'});hub.verified_backends={'twain32:alternate'} if verified else set()
    if started:(dialog.folder/'acquisition.started').touch()
    calls=[];monkeypatch.setattr(dialog,'connect_device',lambda:calls.append('connect'))
    hub.scanner_error('Injected pre-transfer failure');assert len(calls)==expected
    if expected:assert dialog.retry_request['region']==[0,0,210,297]

@pytest.mark.parametrize('available,maximum,expected',[(3,2,2),(2,5,2)])
def test_real_wia_script_with_simulated_feeder(tmp_path,available,maximum,expected):
    if os.name!='nt':pytest.skip('Windows PowerShell protocol test')
    fixture=tmp_path/'fixture.bmp';Image.new('RGB',(30,40),'white').save(fixture);folder=tmp_path/'acquisition';folder.mkdir()
    request=dict(action='scan',device='simulated',item='feeder',dpi=300,color='color',region=[0,0,20,30],max_pages=maximum,folder=str(folder),cancel=str(folder/'cancel.request'))
    request_path=tmp_path/'request.json';request_path.write_text(json.dumps(request))
    script=tmp_path/'fake-device.ps1';script.write_text(r'''
$ErrorActionPreference='Stop'
$global:transfers=0
function P($id,$value,$max=4000) {return [pscustomobject]@{PropertyID=$id;Value=$value;SubType=3;SubTypeValues=@($value);SubTypeMax=$max}}
$global:item=[pscustomobject]@{ItemID='feeder';Items=@();Formats=@('{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}');Properties=@((P 4125 'fe131934-f84c-42ad-8da4-6129cddd7288'),(P 3096 1),(P 3088 1),(P 6146 1),(P 4103 3),(P 6147 300),(P 6148 300),(P 6149 0),(P 6150 0),(P 6151 2550),(P 6152 3300))}
$item | Add-Member ScriptMethod Transfer {
    param($format)
    $global:transfers++
    if ($global:transfers -gt [int]$env:FAKE_AVAILABLE) {throw [System.Runtime.InteropServices.COMException]::new('Feeder empty',-2145320957)}
    $image=[pscustomobject]@{Width=30;Height=40}
    $image | Add-Member ScriptMethod SaveFile {param($path) [System.IO.File]::WriteAllBytes($path,[System.IO.File]::ReadAllBytes($env:FAKE_BITMAP))}
    return $image
}
$global:device=[pscustomobject]@{Items=@($global:item)}
$info=[pscustomobject]@{DeviceID='simulated'};$info | Add-Member ScriptMethod Connect {return $global:device}
$global:manager=[pscustomobject]@{DeviceInfos=@($info)}
function New-Object {
    param([string]$ComObject,[Parameter(Position=0)][string]$TypeName,[Parameter(Position=1)]$ArgumentList)
    if ($ComObject) {if($ComObject -ne 'WIA.DeviceManager'){throw 'Unexpected real COM request'};return $global:manager}
    return Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList
}
[Console]::SetIn([System.IO.StringReader]::new([System.IO.File]::ReadAllText($env:FAKE_REQUEST)))
. $env:FAKE_BRIDGE
''',encoding='utf-8')
    env=dict(os.environ,FAKE_AVAILABLE=str(available),FAKE_BITMAP=str(fixture),FAKE_REQUEST=str(request_path),FAKE_BRIDGE=str(Path('app/services/wia_bridge.ps1').resolve()))
    result=subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],input=(json.dumps(request)+'\n').encode(),env=env,capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    text=result.stdout.decode('utf-8-sig');assert text.strip(),result.stderr.decode(errors='replace');payload=json.loads(text.strip().splitlines()[-1]);assert payload['ok'],(text,result.stderr)
    driver=payload['result'];assert len(driver['pages'])==expected and (folder/'acquisition.started').exists()
    inspected=inspect_scans(folder,driver['pages'],{'driver':driver});assert len(inspected['pages'])==expected
    assert all(Path(p['original']).read_bytes()==fixture.read_bytes() for p in inspected['pages'])
    assert driver['limit_reached']==(available>=maximum)

def test_feeder_duplicate_page_is_rejected_without_overwriting(tmp_path):
    folder=tmp_path/'batch';page=folder/'page-0001';page.mkdir(parents=True);path=page/'original.bmp';Image.new('RGB',(20,30)).save(path);before=path.read_bytes()
    with pytest.raises(ValueError,match='duplicate'):inspect_scans(folder,[{'path':str(path)},{'path':str(path)}],{})
    assert path.read_bytes()==before

@pytest.mark.parametrize('factor',['1.25','1.5','2'])
def test_scaled_native_desktop_keeps_workspaces_reachable(tmp_path,factor):
    import sys
    base=Path(__file__).resolve().parents[1];output=tmp_path/'scale-review'
    env=dict(os.environ,LOCALAPPDATA=str(tmp_path/'scaled-user'),PRINTORA_FINAL_VERIFY='1',QT_QPA_PLATFORM='windows' if os.name=='nt' else 'offscreen',QT_SCALE_FACTOR=factor)
    result=subprocess.run([sys.executable,str(base/'main.py'),'--verify-final-studio',str(output)],cwd=base,env=env,capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    data=json.loads((output/'result.json').read_text());assert result.returncode==0 and data['passed'],data
    assert len(data['checks'])==25 and not data['physical_acquisition'] and not data['physical_print']
    assert {'NID Front and Back share the paper horizontal center',
            'NID Front and Back center vertically as a complete group'}.issubset(data['checks'])

@pytest.mark.parametrize('key,raw',[('document_landscape','[]'),('document_color','{}'),('document_paper_mm','[true,297]'),('document_paper_mm','[0,297]')])
def test_new_document_defaults_recover_bad_optional_values(tmp_path,key,raw):
    from app.core.database import Database
    from app.services.hardware import HARDWARE_DEFAULTS
    db=Database(tmp_path/'studio.db');db.conn.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(key,raw));db.conn.commit()
    assert db.get(key)==HARDWARE_DEFAULTS[key] and db.preference_diagnostics
    assert db.conn.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()[0]==raw;db.conn.close()
