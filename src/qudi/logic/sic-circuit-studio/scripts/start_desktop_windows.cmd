@echo off
setlocal
pushd "%~dp0.."
py -3 desktop.py
if errorlevel 1 (
  echo.
  echo Desktop mode needs Windows Python and pywebview.
  echo Install with: py -3 -m pip install pywebview
  pause
)
popd
