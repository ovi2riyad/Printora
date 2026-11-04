@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" main.py
) else if exist ".tools\python\pythonw.exe" (
  start "" ".tools\python\pythonw.exe" main.py
) else (
  echo Run setup.bat first.
  pause
)
