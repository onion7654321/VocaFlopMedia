@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\flet.exe" (
  echo Run install_windows.bat first.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m unittest discover -s tests -q
if errorlevel 1 goto failed
flet pack main.py --name Vocaflop --icon assets\logo.ico --onedir --yes
if errorlevel 1 goto failed
echo.
echo EXE: dist\Vocaflop\Vocaflop.exe
echo Distribute the entire dist\Vocaflop directory, not just the EXE.
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
