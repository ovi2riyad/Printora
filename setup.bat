@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto error
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Setup complete. Double-click run.bat.
pause
exit /b 0
:error
echo Setup failed. Install Python 3.12 x64 from python.org and enable Add Python to PATH.
pause
exit /b 1
