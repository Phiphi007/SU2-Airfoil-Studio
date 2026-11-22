@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3.11 or 3.12 was not found.
    echo Install Python from https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
  set "PYTHON_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating the local Python environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :failed
)

echo [2/3] Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo [3/3] Installing project dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Setup complete. Add SU2_CFD.exe to PATH, then run Launch_SU2_Airfoil_Qt.bat.
pause
exit /b 0

:failed
echo.
echo [ERROR] Setup failed. Check the messages above and your network connection.
pause
exit /b 1
