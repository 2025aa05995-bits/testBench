@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [ERROR] .venv not found. Run setup.bat first.
  pause
  exit /b 1
)

echo.
echo Installing hardware-related Python packages into:
echo   %VPY%
echo.
echo Using --no-cache-dir to reduce "Access denied" on pip cache folders.
echo Close VS Code/Cursor/terminals that might lock .venv before continuing.
echo.
pause

"%VPY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [WARN] pip upgrade failed; continuing.
)

"%VPY%" -m pip install --no-cache-dir -r "%~dp0requirements-hardware.txt"
if errorlevel 1 (
  echo.
  echo [RETRY] Explicit package install ...
  "%VPY%" -m pip install --no-cache-dir "pyvisa>=1.14.0" "pyvisa-py>=0.7.0" "pyserial>=3.5"
)

if errorlevel 1 (
  echo.
  echo [FAILED] Still could not install. Common fixes:
  echo   - Clone or copy the repo to %%USERPROFILE%%\projects\testBench ^(not Program Files^).
  echo   - Windows Security: allow Python / pip for this folder.
  echo   - If the project is under OneDrive, pause sync or move it outside OneDrive.
  echo   - Right-click this script → Run as administrator ^(last resort^).
  echo.
  pause
  exit /b 1
)

echo.
echo [OK] Hardware packages installed. Test:  "%VPY%" -c "import pyvisa; print('pyvisa OK')"
echo.
pause
exit /b 0
