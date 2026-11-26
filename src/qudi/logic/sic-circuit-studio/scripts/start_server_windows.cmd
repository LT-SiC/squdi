@echo off
setlocal
pushd "%~dp0.."
echo SiC Circuit Studio (local browser server)
echo Visit http://127.0.0.1:8765 in your browser.
echo Keep this window open. Press Ctrl+C to stop.
py -3 server.py
if errorlevel 1 pause
popd
