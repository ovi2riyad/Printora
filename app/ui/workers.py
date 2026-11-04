import traceback
from PySide6.QtCore import QObject,Signal,QRunnable

class Signals(QObject):
    done=Signal(object)
    error=Signal(str)

class Worker(QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=Signals()
    def run(self):
        try:self.signals.done.emit(self.fn())
        except Exception as e:self.signals.error.emit(str(e)+'\n\n'+traceback.format_exc())
