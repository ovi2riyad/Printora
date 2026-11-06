@echo off
cd /d "%~dp0"
set "STUDIO_PYTHON=.venv\Scripts\python.exe"
if not exist "%STUDIO_PYTHON%" set "STUDIO_PYTHON=.tools\python\python.exe"
"%STUDIO_PYTHON%" -m scripts.build_release %*
if errorlevel 1 goto error
echo Candidate ready: dist\candidate\StudioPhotoMaker\StudioPhotoMaker.exe
echo Windows Setup is in dist\installers unless --portable-only was selected.
echo Validate this candidate before replacing a working release.
pause
exit /b 0
:error
echo Build failed. Check dependencies, portrait model, and Inno compiler setup.
pause
exit /b 1
