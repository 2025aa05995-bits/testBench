@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ---------------------------------------------------------------------------
rem  TestBench — Windows setup (venv + dependencies + smoke checks)
rem  Run from an elevated or normal prompt; double-click is OK.
rem ---------------------------------------------------------------------------

cd /d "%~dp0"
set "ROOT=%CD%"

echo.
echo ==========================================
echo   TestBench — Windows setup
echo ==========================================
echo   Folder: %ROOT%
echo.

rem ----- Python 3.10+ (prefer py launcher, pin newer minors first) -----
set "PYW="
if exist "%SystemRoot%\py.exe" set "HAS_PY=1"
where py >nul 2>&1 && set "HAS_PY=1"

if defined HAS_PY (
  for %%V in (3.13 3.12 3.11 3.10 3) do (
    if not defined PYW (
      py -%%V -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)" 2>nul
      if not errorlevel 1 set "PYW=py -%%V"
    )
  )
)

if not defined PYW (
  where python >nul 2>&1 && (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)" 2>nul
    if not errorlevel 1 set "PYW=python"
  )
)

if not defined PYW (
  echo [ERROR] Python 3.10 or newer not found.
  echo.
  echo Install Python from https://www.python.org/downloads/windows/
  echo   - Check "Add python.exe to PATH"
  echo   - Prefer the full installer ^(includes Tcl/Tk if PyQt is unavailable^)
  echo   - Or install the "Python Launcher for Windows"
  echo.
  exit /b 1
)

echo [OK] Using: %PYW%
%PYW% -c "import sys; print('     version:', sys.version.split()[0])"
echo.

rem ----- virtual environment -----
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo Creating virtual environment: .venv
  %PYW% -m venv "%ROOT%\.venv"
  if errorlevel 1 (
    echo [ERROR] Could not create .venv ^(try running as normal user with Python installed^).
    exit /b 1
  )
  echo [OK] Virtual environment created.
) else (
  echo [OK] Existing .venv found.
)

if not exist "%VENV_PY%" (
  echo [ERROR] Missing "%VENV_PY%"
  exit /b 1
)

rem ----- pip toolchain -----
echo.
echo Upgrading pip, setuptools, wheel ...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [WARN] pip upgrade reported an error; continuing.
)

rem ----- runtime + dev requirements -----
echo.
echo Installing requirements.txt ...
"%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 (
  echo [ERROR] pip install -r requirements.txt failed.
  echo        Check network/proxy and try again.
  exit /b 1
)
echo [OK] requirements.txt installed.

rem ----- optional hardware (VISA/serial) -----
if exist "%ROOT%\requirements-hardware.txt" (
  echo.
  if /i "%SETUP_NONINTERACTIVE%"=="1" (
    echo Non-interactive ^(SETUP_NONINTERACTIVE=1^): skipping hardware packages.
  ) else (
    rem Default N after 12s so a quick double-click still finishes setup
    choice /T 12 /D N /C YN /M "Install hardware drivers (pyvisa/pyserial) for real instruments? "
    set "HWCHO=!ERRORLEVEL!"
    if "!HWCHO!"=="1" (
      echo Installing requirements-hardware.txt into .venv ...
      rem --no-cache-dir avoids "Access denied" on some PCs (pip cache / AV / policy)
      "%VENV_PY%" -m pip install --no-cache-dir -r "%ROOT%\requirements-hardware.txt"
      if errorlevel 1 (
        echo.
        echo [RETRY] Second attempt ^(explicit packages, no cache^) ...
        "%VENV_PY%" -m pip install --no-cache-dir "pyvisa>=1.14.0" "pyvisa-py>=0.7.0" "pyserial>=3.5"
      )
      if errorlevel 1 (
        call :hardware_install_failed
      ) else (
        echo [OK] Hardware extras installed.
      )
    ) else (
      echo Skipping hardware extras ^(simulated instruments work without them^).
    )
  )
)

rem ----- verify imports -----
echo.
echo Verifying GUI stack ...
"%VENV_PY%" -c "import PyQt5.QtWidgets; print('  PyQt5: OK')" 2>nul
if errorlevel 1 (
  echo [ERROR] PyQt5 import failed. GUI needs PyQt5 wheels for your Python version.
  echo        Re-run after fixing:  "%VENV_PY%" -m pip install --force-reinstall PyQt5
  exit /b 1
)
"%VENV_PY%" -c "import matplotlib; print('  matplotlib:', matplotlib.__version__)" 2>nul
if errorlevel 1 goto :verify_fail
"%VENV_PY%" -c "import PIL; print('  Pillow: OK')" 2>nul
if errorlevel 1 goto :verify_fail
"%VENV_PY%" -c "import openai; print('  openai: OK')" 2>nul
if errorlevel 1 goto :verify_fail
"%VENV_PY%" -c "import sys; sys.path.insert(0, r'%ROOT%\src'); import testbench.command_registry; print('  testbench: OK')" 2>nul
if errorlevel 1 goto :verify_fail

echo.
echo Smoke test: loading gui_chat.py ^(no window^) ...
"%VENV_PY%" -c "import runpy; runpy.run_path(r'%ROOT%\gui_chat.py', run_name='__setup_smoke__')" 2>nul
if errorlevel 1 (
  echo [ERROR] gui_chat.py failed to load. See message above.
  exit /b 1
)
echo [OK] gui_chat imports cleanly.

rem ----- config sanity -----
if not exist "%ROOT%\config\testbenchconfig.json" (
  echo.
  echo [WARN] config\testbenchconfig.json is missing. Copy or create one before running instruments.
)

echo.
echo ==========================================
echo   Setup finished successfully.
echo ==========================================
echo.
echo Start the GUI:
echo   run_gui.bat
echo   ^(or:  "%VENV_PY%" "%ROOT%\gui_chat.py" ^)
echo.
echo Hardware ^(pyvisa/serial^) failed or skipped? Run:  install_hardware.bat
echo Tip: silent / automated install:  set SETUP_NONINTERACTIVE=1 ^&^& setup.bat
echo.
if /i not "%SETUP_NONINTERACTIVE%"=="1" pause
exit /b 0

:verify_fail
echo [ERROR] Dependency verification failed.
exit /b 1

:hardware_install_failed
echo.
echo [WARN] Hardware packages could not be installed. Simulation mode still works.
echo.
echo If you saw "Access denied" or "Permission denied":
echo   1. Put the repo in a folder you own ^(e.g. %%USERPROFILE%%\source\testBench^), not Program Files.
echo   2. Close IDEs/terminals using this .venv, then run:  install_hardware.bat
echo   3. Pause OneDrive/antivirus scanning on this folder if it locks .venv.
echo   4. Last resort: right-click install_hardware.bat → Run as administrator.
echo.
exit /b 0

