"""Windows shell identity and installer detection; no elevation for normal use."""
import os
import atexit


def configure_shell():
    if os.name!='nt':return
    import ctypes
    from ctypes import wintypes
    from app.version import APP_USER_MODEL_ID
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=(ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR);kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=kernel.CreateMutexW(None,False,r'Local\Printora.Desktop.Running')
    if handle:atexit.register(kernel.CloseHandle,handle)
