@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VPY=%~dp0.venv\Scripts\python.exe"
set "GUI=%~dp0gui_chat.py"

if not exist "%VPY%" (
  echo [ERROR] Virtual environment not found.
  echo Run setup.bat first, then try again.
  pause
  exit /b 1
)

if not exist "%GUI%" (
  echo [ERROR] gui_chat.py not found at %GUI%
  pause
  exit /b 1
)

"%VPY%" "%GUI%"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo GUI exited with code %EC%.
  pause
)
exit /b %EC%
