@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found. Run Setup_Windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m qt_app.main
if errorlevel 1 pause
