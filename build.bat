@echo off
cd /d "%~dp0"
set "STUDIO_PYTHON=.venv\Scripts\python.exe"
if not exist "%STUDIO_PYTHON%" set "STUDIO_PYTHON=.tools\python\python.exe"
"%STUDIO_PYTHON%" -m PyInstaller --noconfirm StudioPhotoMaker.spec
pause
