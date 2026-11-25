@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto failed
)
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Vocaflop ready. Use run_windows.bat
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.10+ and check your connection.
pause
exit /b 1
