@echo off
cd /d "%~dp0"
set "STUDIO_PYTHON=.venv\Scripts\python.exe"
if not exist "%STUDIO_PYTHON%" set "STUDIO_PYTHON=.tools\python\python.exe"
"%STUDIO_PYTHON%" -m PyInstaller --clean --noconfirm --distpath dist\candidate --workpath build\candidate StudioPhotoMaker.spec
if errorlevel 1 goto error
echo Candidate ready: dist\candidate\StudioPhotoMaker\StudioPhotoMaker.exe
echo Validate this candidate before replacing a working release.
pause
exit /b 0
:error
echo Build failed. Check dependencies and the installed portrait model.
pause
exit /b 1
