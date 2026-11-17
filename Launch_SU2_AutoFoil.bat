@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "PYTHONW_EXE=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Project virtual environment was not found. Run: python -m venv .venv, then install requirements.txt','SU2 AutoFoil Studio')" >nul
  exit /b 1
)

rem Some portable Python runtimes cannot initialize Tcl/Tk directly from their cache path.
rem Cache a local copy on first launch so the GUI starts reliably by double-clicking this BAT.
set "LOCAL_TCL_ROOT=%~dp0.runtime\tcl"
rem Read the venv base path without nested command-line quotes (paths may contain spaces).
for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"home =" "%~dp0.venv\pyvenv.cfg"') do set "PYTHON_BASE=%%B"
set "PYTHON_BASE=%PYTHON_BASE:~1%"
if not exist "%LOCAL_TCL_ROOT%\tcl8.6\init.tcl" (
  if not exist "%PYTHON_BASE%\tcl\tcl8.6\init.tcl" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Tcl/Tk runtime was not found. Please rebuild .venv with an official Python 3.11 or 3.12 installation.','SU2 AutoFoil Studio')" >nul
    exit /b 1
  )
  mkdir "%LOCAL_TCL_ROOT%" >nul 2>&1
  xcopy "%PYTHON_BASE%\tcl\tcl8.6\*" "%LOCAL_TCL_ROOT%\tcl8.6\" /E /I /Q /Y >nul
  xcopy "%PYTHON_BASE%\tcl\tk8.6\*" "%LOCAL_TCL_ROOT%\tk8.6\" /E /I /Q /Y >nul
)
if not exist "%LOCAL_TCL_ROOT%\tk8.6\tk.tcl" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('The local Tcl/Tk runtime cache is incomplete. Delete the .runtime folder and launch again.','SU2 AutoFoil Studio')" >nul
  exit /b 1
)
set "TCL_LIBRARY=%LOCAL_TCL_ROOT%\tcl8.6"
set "TK_LIBRARY=%LOCAL_TCL_ROOT%\tk8.6"

where SU2_CFD.exe >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('SU2_CFD.exe was not found in PATH. Add the SU2 bin directory to PATH first.','SU2 AutoFoil Studio')" >nul
  exit /b 1
)

start "SU2 AutoFoil Studio" /D "%~dp0" "%PYTHONW_EXE%" "%~dp0gui_app.py"
exit /b 0
