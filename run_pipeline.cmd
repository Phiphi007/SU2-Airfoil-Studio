@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Virtual environment not found: %PYTHON_EXE%
  echo Run: python -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

"%PYTHON_EXE%" "%PROJECT_DIR%main_pipeline.py" %*
exit /b %errorlevel%
