@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\package_release.py
if errorlevel 1 (
  echo Packaging failed. Check the build output above.
  pause
  exit /b 1
)
echo Upload the ZIP and SHA256SUMS.txt from the release folder.
pause
