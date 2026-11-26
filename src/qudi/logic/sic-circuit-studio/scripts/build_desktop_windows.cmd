@echo off
setlocal
pushd "%~dp0.."
py -3 -m pip install pywebview pyinstaller
if errorlevel 1 goto failed
py -3 -m PyInstaller --noconfirm --clean --onedir --windowed --name SiC-Circuit-Studio --icon "frontend\studio.ico" --add-data "frontend;frontend" --hidden-import backend.legacy_mcas desktop.py
if errorlevel 1 goto failed
echo.
echo Windows desktop build: dist\SiC-Circuit-Studio\SiC-Circuit-Studio.exe
echo Rebuild after updating the Python/frontend source if you use the compiled .exe.
popd
exit /b 0
:failed
echo Build failed. See the message above.
pause
popd
exit /b 1
