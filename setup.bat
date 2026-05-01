@echo off
setlocal enableextensions

rem One-click Windows setup for TestBench
cd /d "%~dp0"

echo.
echo ==========================================
echo   TestBench - One Click Setup (Windows)
echo ==========================================
echo.

rem Find a Python executable (prefer py launcher)
set "PYEXE="
where py >nul 2>nul
if %errorlevel%==0 (
  set "PYEXE=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PYEXE=python"
  )
)

if "%PYEXE%"=="" (
  echo ERROR: Python not found.
  echo - Install Python 3.10+ from Microsoft Store or python.org
  echo - Then re-run this script.
  exit /b 1
)

rem Create venv if missing
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  %PYEXE% -m venv ".venv"
  if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment.
    exit /b 1
  )
)

echo Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if %errorlevel% neq 0 (
  echo ERROR: Failed to upgrade pip.
  exit /b 1
)

echo Installing dependencies (requirements.txt) ...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if %errorlevel% neq 0 (
  echo ERROR: Failed to install requirements.txt
  exit /b 1
)

if exist "requirements-hardware.txt" (
  echo.
  choice /c YN /n /m "Install optional hardware connectivity packages (pyvisa/pyserial)? [Y/N] " < con
  set "CHOICERESULT=%errorlevel%"
  if "%CHOICERESULT%"=="1" goto install_hw
  goto skip_hw
)
goto after_hw

:install_hw
echo Installing optional hardware dependencies (requirements-hardware.txt) ...
".venv\Scripts\python.exe" -m pip install -r "requirements-hardware.txt"
if %errorlevel% neq 0 (
  echo ERROR: Failed to install requirements-hardware.txt
  exit /b 1
)
goto after_hw

:skip_hw
echo Skipping optional hardware dependencies.

:after_hw

echo.
echo ==========================================
echo Setup complete.
echo.
echo Run the GUI:
echo   .\.venv\Scripts\python.exe .\gui_chat.py
echo ==========================================
echo.
pause
exit /b 0

