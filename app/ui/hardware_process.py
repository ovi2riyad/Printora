"""Bounded one-operation processes. Native drivers never execute in the GUI process."""
from pathlib import Path
import json
import os
import sys
import uuid
from PySide6.QtCore import QObject, QProcess, QTimer, Signal


def driver_message(result):
    code=result.get('hresult',0)
    code=(code & 0xffffffff) if isinstance(code,int) else 0
    states={0x80210006:'Busy — another application or operation owns the scanner',
            0x8021000D:'Busy — scanner is locked',0x80210005:'Offline — check power and connection',
            0x80210009:'Not Found — scanner was removed',0x80210015:'Not Found — no scanner available',
            0x8021000A:'Offline / communication error — check the connection',
            0x80210016:'Error — close the scanner cover',0x80040154:'Driver Unavailable — WIA Automation is not installed'}
    return states.get(code,'Error')+': '+result.get('error','Device driver failed')


class HardwareProcess(QObject):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.timer = QTimer(self); self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.output = bytearray(); self.error = bytearray(); self.expired = False
        self.result_path=None
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_error)

    @property
    def active(self):
        return self.process.state() != QProcess.NotRunning

    def start(self, kind, request, timeout=20000):
        if self.active:
            raise ValueError('A device operation is already in progress')
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        if kind in ('wia','twain32'):
            if os.name != 'nt':
                raise ValueError('WIA requires Windows and an installed scanner driver')
            program = str(Path(os.environ['SystemRoot'])/('SysWOW64' if kind=='twain32' else 'System32')/'WindowsPowerShell/v1.0/powershell.exe')
            args = ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-STA', '-ExecutionPolicy', 'Bypass', '-File',
                    str(root/'app/services'/('twain_bridge.ps1' if kind=='twain32' else 'wia_bridge.ps1'))]
            self.result_path=None
        else:
            from app.core.database import data_root
            folder=data_root()/'hardware-requests'/uuid.uuid4().hex;folder.mkdir(parents=True,exist_ok=False)
            request_path=folder/'request.json';self.result_path=folder/'result.json'
            with request_path.open('x',encoding='utf-8') as stream:json.dump(request,stream)
            program = sys.executable
            args = ([] if getattr(sys, 'frozen', False) else [str(root/'main.py')]) + ['--hardware-worker',str(request_path),str(self.result_path)]
        self.output.clear(); self.error.clear(); self.expired = False
        self.process.blockSignals(False)
        self.process.setProgram(program); self.process.setArguments(args)
        self.process.start()
        self.process.write((json.dumps(request, ensure_ascii=True)+'\n').encode('utf-8'))
        self.process.closeWriteChannel()
        self.timer.start(timeout)

    def read_output(self):
        self.output.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.output) > 2_000_000:
            self.timeout()

    def read_error(self):
        self.error.extend(bytes(self.process.readAllStandardError()))
        if len(self.error) > 100_000:
            del self.error[:-100_000]

    def timeout(self):
        self.expired = True
        self.process.kill()

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.timer.stop(); self.failed.emit('Driver helper unavailable. Check Windows components and refresh devices.')

    def finished(self, code, status):
        self.timer.stop(); self.read_output(); self.read_error()
        if self.expired:
            self.failed.emit('Device operation timed out. Completed scan files are retained. Printing may be partial; check the queue before retrying.')
            return
        try:
            if self.result_path:
                if self.result_path.stat().st_size>2_000_000:raise ValueError('Device response too large')
                result=json.loads(self.result_path.read_text(encoding='utf-8'))
            else:result = json.loads(self.output.decode('utf-8-sig').strip())
            if not result['ok']:
                raise ValueError(driver_message(result))
            if code != 0:
                raise ValueError('Device helper exited unexpectedly')
            self.succeeded.emit(result['result'])
        except (ValueError, KeyError, UnicodeError,OSError) as error:
            self.failed.emit(str(error) if self.output or self.result_path else 'Driver helper failed without a result. Check the installed driver and reconnect the device.')

    def shutdown(self):
        self.timer.stop()
        self.process.blockSignals(True)
        if self.active:
            self.process.kill()
            self.process.waitForFinished(1500)
