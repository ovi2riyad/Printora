@echo off
cd /d "%~dp0"
set "STUDIO_PYTHON=.venv\Scripts\python.exe"
if not exist "%STUDIO_PYTHON%" set "STUDIO_PYTHON=.tools\python\python.exe"
if not exist "%STUDIO_PYTHON%" goto error
"%STUDIO_PYTHON%" -m scripts.build_release %*
if errorlevel 1 goto error
echo Client Setup EXE is printed above, in dist\installers unless --output was specified.
echo Double-click Setup to install to C:\Printora. End users do not need Python.
echo The EXE inside the portable folder is the application, not the installer.
if not defined PRINTORA_BUILD_NO_PAUSE pause
exit /b 0
:error
echo Build failed. Check dependencies, portrait model, and Inno compiler setup.
if not defined PRINTORA_BUILD_NO_PAUSE pause
exit /b 1
