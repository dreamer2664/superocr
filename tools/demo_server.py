#!/usr/bin/env python3
"""superocr S4 — browser demo with measured latency (t-20261011-27bc).

Single-file HTTP server (stdlib only) that serves tools/demo.html and one
endpoint, POST /ocr. The endpoint calls the SAME recognition path the CLI
typer uses (typer.recognise -> reader.read_chain): the demo is not a
parallel implementation, it is the pipeline with a browser bolted on.

Every /ocr response carries server_ms — wall time spent inside the shared
recognise() call, measured on the server. The page keeps its own rolling
end-to-end times too. tools/demo_latency.py hammers /ocr and reports the
median, because a demo's latency claim must come from repeated measured
runs, not from one lucky click.

Usage: python3 tools/demo_server.py [--port 8420] [--host 0.0.0.0]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import typer as T  # noqa: E402  (imports generator + reader via it)

HTML = (Path(__file__).resolve().parent / "demo.html").read_text(encoding="utf-8")
MAX_UPLOAD = 4 * 1024 * 1024  # 4 MiB is generous for a captcha-sized demo


class Handler(BaseHTTPRequestHandler):
    server_version = "superocr-demo/1.0"

    def log_message(self, fmt, *args):  # keep stdout readable
        pass

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not-found"})

    def do_POST(self):
        if self.path != "/ocr":
            self._json(404, {"error": "not-found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            self._json(413, {"error": "upload-empty-or-too-large",
                             "limit_bytes": MAX_UPLOAD})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
            data = base64.b64decode(payload["image"])
            family = str(payload.get("family", "auto"))
        except Exception:
            self._json(400, {"error": "bad-payload",
                             "hint": "send JSON {image: base64, family?: str}"})
            return
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            self._json(400, {"error": "not-an-image"})
            return
        t0 = time.perf_counter()
        try:
            text, conf, fam = T.recognise(img, family)
        except SystemExit as e:  # reader dies honestly; so do we
            self._json(422, {"error": "reader-refused", "detail": str(e)})
            return
        except Exception as e:
            self._json(500, {"error": "reader-failed", "detail": repr(e)})
            return
        server_ms = (time.perf_counter() - t0) * 1000.0
        avg = round(sum(conf) / len(conf), 3) if conf else 0.0
        self._json(200, {"text": text, "family": fam,
                         "avg_confidence": avg,
                         "server_ms": round(server_ms, 1)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8420)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"superocr demo on http://{args.host}:{args.port} "
          f"(POST /ocr, GET /health) — Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
