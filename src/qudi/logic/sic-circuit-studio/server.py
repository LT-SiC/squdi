"""Local web app. No external dependencies; localhost only for safety."""
from __future__ import annotations
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from backend.circuit import CircuitError, normalize, export, summarize, VERSION

ROOT = Path(__file__).resolve().parent / 'frontend'
STATIC = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/measurement_extras.js': 'measurement_extras.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg', '/startup.html': 'startup.html', '/startup.js': 'startup.js', '/manifest.webmanifest': 'manifest.webmanifest', '/icon-192.png': 'icon-192.png', '/icon-512.png': 'icon-512.png'}
MAX_BODY = 1024 * 1024

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, mime):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.send_json(200, {'ok': True, 'version': VERSION, 'hardware_connected': False})
        if path not in STATIC:
            return self.send_json(404, {'error': 'Not found'})
        file = ROOT / STATIC[path]
        payload = file.read_bytes()
        self.send_bytes(200, payload, mimetypes.guess_type(str(file))[0] or 'application/octet-stream')

    def do_POST(self):
        if urlsplit(self.path).path != '/api/export':
            return self.send_json(404, {'error': 'Not found'})
        try:
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                return self.send_json(415, {'error': 'Expected application/json'})
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= MAX_BODY:
                return self.send_json(413, {'error': 'Request too large or empty'})
            payload = json.loads(self.rfile.read(n))
            circuit = normalize(payload.get('circuit'))
            output = export(circuit, payload.get('format', 'qasm'))
            return self.send_json(200, {'circuit': circuit, 'code': output, 'summary': summarize(circuit)})
        except (CircuitError, ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
            return self.send_json(400, {'error': str(exc)})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as httpd:
        print(f'SiC Circuit Studio v{VERSION} at http://127.0.0.1:{args.port}', flush=True)
        httpd.serve_forever()
