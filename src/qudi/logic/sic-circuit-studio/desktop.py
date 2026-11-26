"""Optional native desktop window using pywebview and the SAME frontend/backend.

On Windows: py -3 -m pip install pywebview
            py -3 desktop.py

The local server binds to 127.0.0.1 on a random ephemeral port. No network
connections or measurement hardware are enabled. This is not a Qudi client.
"""
from __future__ import annotations
import sys
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

try:
    import webview
except ImportError:
    raise SystemExit('Desktop mode requires pywebview. Install with: py -3 -m pip install pywebview')

import server

# PyInstaller extracts --add-data frontend to sys._MEIPASS in a frozen build.
if getattr(sys, 'frozen', False):
    server.ROOT = Path(sys._MEIPASS) / 'frontend'


def main():
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{httpd.server_address[1]}/startup.html'
    try:
        webview.create_window('SiC Circuit Studio', url=url, width=1380, height=860,
                              min_size=(870, 580), background_color='#102b33')
        webview.start(debug=False)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


if __name__ == '__main__':
    main()
