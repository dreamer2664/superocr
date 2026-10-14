#!/usr/bin/env python3
"""Local, bounded synthetic CAPTCHA studio. No external services or label-fed OCR."""
from __future__ import annotations

import argparse
from collections import OrderedDict
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlsplit
import webbrowser

APP = Path(__file__).resolve().parent
ROOT = APP.parent.parent
sys.path.insert(0, str(APP))
import engine as E

MAX_BODY = 16384
CACHE_LIMIT = 128
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}


class Studio:
    def __init__(self, reader=None, package=None):
        self.lock = threading.RLock()
        self.generate_lock = threading.Lock()
        self.ocr_lock = threading.Lock()
        self.items = OrderedDict()
        self.reader = reader or E.recognize
        self.package = Path(package).resolve() if package else None

    def create(self, payload):
        if not self.generate_lock.acquire(blocking=False):
            raise BlockingIOError('Another batch is generating; try again shortly')
        try:
            config, items = E.generate(payload)
            with self.lock:
                for png, row in items:
                    self.items[row['id']] = (png, row)
                    self.items.move_to_end(row['id'])
                while len(self.items) > CACHE_LIMIT:
                    self.items.popitem(last=False)
            return {'config': config, 'items': [{**row, 'url': f'/api/image/{row["id"]}.png'}
                                               for _, row in items],
                    'recipe': E.RECIPE, 'count': len(items),
                    'note': 'Only the latest 128 images are kept in server memory.'}
        finally:
            self.generate_lock.release()

    def get(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{24}', identifier):
            raise ValueError('Invalid image identifier')
        with self.lock:
            if identifier not in self.items:
                raise KeyError('Image expired or is unknown; regenerate this batch')
            return self.items[identifier]

    def read(self, identifier):
        png, row = self.get(identifier)
        if not self.ocr_lock.acquire(blocking=False):
            raise BlockingIOError('The reader is busy; wait for the current image')
        try:
            # This boundary deliberately passes PNG bytes ONLY to the reader.
            result = self.reader(png)
            return {'id': identifier, **E.compare_result(result, row['label'])}
        finally:
            self.ocr_lock.release()

    def export(self, identifiers):
        if (not isinstance(identifiers, list) or not 1 <= len(identifiers) <= E.MAX_COUNT
                or any(not isinstance(i, str) for i in identifiers)):
            raise ValueError('Export requires a list of 1–32 image IDs')
        with self.lock:
            return E.export_zip([self.get(identifier) for identifier in identifiers])


class Handler(BaseHTTPRequestHandler):
    server_version = 'CaptchaStudio/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(90)  # bound incomplete HTTP headers/bodies

    def log_message(self, fmt, *args):
        # Request bodies / custom labels are never logged.
        sys.stderr.write('studio: ' + fmt % args + '\n')

    def send(self, status, body, mime='application/json; charset=utf-8', filename=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; img-src 'self' data: blob:; "
                         "style-src 'self'; script-src 'self'; connect-src 'self'; "
                         "object-src 'none'; base-uri 'none'")
        # No frame-ancestors/X-Frame-Options block: the Arena live preview embeds us.
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, status, payload):
        self.send(status, json.dumps(payload, ensure_ascii=True).encode())

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC:
            name, mime = STATIC[path]
            return self.send(200, (APP / 'static' / name).read_bytes(), mime)
        if path == '/api/health':
            return self.json(200, {'ok': True, 'build': E.build_info(),
                'families': E.FAMILIES, 'max_count': E.MAX_COUNT, 'max_text': E.MAX_TEXT,
                'download_available': bool(self.server.studio.package and self.server.studio.package.is_file())})
        if path == '/api/app-download':
            p = self.server.studio.package
            if p and p.is_file():
                return self.send(200, p.read_bytes(), 'application/zip', p.name)
            return self.json(404, {'error': 'No package attached to this development server'})
        match = re.fullmatch(r'/api/image/([a-f0-9]{24})\.png', path)
        if match:
            try:
                png, _ = self.server.studio.get(match.group(1))
                return self.send(200, png, 'image/png')
            except KeyError:
                return self.json(404, {'error': 'Image expired; regenerate the batch'})
        return self.json(404, {'error': 'Not found'})

    def do_OPTIONS(self):
        # No cross-origin access to a user's loopback service.
        return self.json(403, {'error': 'Cross-origin access is not supported'})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/generate', '/api/ocr', '/api/export'):
            return self.json(404, {'error': 'Not found'})
        origin = self.headers.get('Origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or parsed.netloc != self.headers.get('Host'):
                return self.json(403, {'error': 'Cross-origin request refused'})
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.json(415, {'error': 'Send application/json'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > MAX_BODY:
                return self.json(413, {'error': 'JSON body must be between 1 and 16384 bytes'})
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Expected a JSON object')
            studio = self.server.studio
            if path == '/api/generate':
                return self.json(200, studio.create(payload))
            if path == '/api/ocr':
                if set(payload) != {'id'}:
                    raise ValueError('OCR accepts an image ID only, never a label or family hint')
                return self.json(200, studio.read(payload['id']))
            if set(payload) != {'ids'}:
                raise ValueError('Export accepts an IDs list only')
            data = studio.export(payload['ids'])
            return self.send(200, data, 'application/zip', 'captcha-studio-samples.zip')
        except BlockingIOError as exc:
            return self.json(409, {'error': str(exc)})
        except KeyError:
            return self.json(404, {'error': 'Image expired or unknown; regenerate this batch'})
        except (ValueError, TypeError, UnicodeError) as exc:
            return self.json(400, {'error': str(exc)})
        except Exception as exc:
            return self.json(500, {'error': 'Operation failed', 'detail': str(exc)[:250]})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, studio=None):
        self.studio = studio or Studio()
        super().__init__(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8488)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--with-ocr', action='store_true', help='include real shipping-route smoke in selftest')
    parser.add_argument('--package', help='trusted local downloadable app ZIP, exposed at a fixed URL')
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.selftest:
        print(json.dumps(E.selftest(args.with_ocr), indent=2), flush=True)
        return 0
    if not 0 <= args.port <= 65535:
        parser.error('port must be in 0..65535')
    with Server((args.host, args.port), Studio(package=args.package)) as server:
        port = server.server_address[1]
        local = f'http://127.0.0.1:{port}'
        print(f'CAPTCHA Studio listening on {args.host}:{port} — {local}', flush=True)
        print('Generator: S53 mechanics / g1-studio-v1. OCR: floor+lex, not a 98/95 claim.', flush=True)
        if args.host not in ('127.0.0.1', 'localhost', '::1'):
            print('Preview/network mode: no authentication. Use only on a trusted network.', flush=True)
        if args.browser:
            threading.Timer(0.8, lambda: webbrowser.open(local)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nStopped by user.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
