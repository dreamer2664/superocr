#!/usr/bin/env python3
"""CAPTCHA Studio — standalone web app (stdlib only; numpy + Pillow required).

Serves a one-page UI plus a small JSON API:
  GET  /                -> the app page
  GET  /api/config      -> engine metadata + available degradations
  POST /api/generate    -> render ONE captcha {png b64, label, params...}
  POST /api/ocr         -> read any posted captcha with the SHIPPING reader
                           route (baseline.read_text -> lex_projection.fix_line)
  GET  /api/selftest    -> run the packaged self-check, returns the checklist

Engine: vendored superocr modules under engine/ (generator + S53 hard-corpus
degradation mechanics adapted for interactive use; shipping reader chain).
Fonts: bundled DejaVu faces under fonts/ — generator._FONT_CANDIDATES is
repointed at them at import time so the same faces rasterize on any machine
(rendered pixels then depend only on FreeType, which we print in /api/config).

Determinism: an item is keyed by (seed, salt, degradation_type, severity).
Same key -> same image and label, always.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parent
ENG = APP / "engine"
sys.path.insert(0, str(ENG))
sys.path.insert(0, str(ENG / "tools"))
sys.path.insert(0, str(ENG / "readers"))

import generator as G                        # noqa: E402

# Repoint the generator's font search at the bundled faces BEFORE any render.
FONTS = APP / "fonts"
G._FONT_CANDIDATES = [str(FONTS / p) for p in (
    "DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSerif.ttf",
    "DejaVuSerif-Bold.ttf",
    "DejaVuSansMono.ttf",
    "DejaVuSansMono-Bold.ttf",
    "DejaVuSansMono-Oblique.ttf",
    "DejaVuSansMono-BoldOblique.ttf",
)]

import baseline as B                         # noqa: E402
from lex_projection import fix_line          # noqa: E402
import gen_hard_corpus as HC                 # noqa: E402

# baseline instantiates its CNN from a CWD-relative "models/..." path; this app
# runs from its own directory, so pre-load the vendored weights and pre-seed
# baseline's module-level cache (_CNN) — the reader then never touches CWD.
import glyphcnn as _GC                       # noqa: E402

if getattr(B, "_CNN", None) is None and (ENG / "models" / "glyphcnn-v2.npz").exists():
    B._CNN = _GC.GlyphCNN.load(str(ENG / "models" / "glyphcnn-v2.npz"))

APP_VERSION = "1.0"
ENGINE_STAMP = "superocr main a530a8f-class (generator + gen_hard_corpus + reader_lex)"

OVERLAY_FAMS = ["spiderweb", "cross-shadow", "strippy", "darts"]
CORROSION_SEVS = list(HC.CORROSION_PITS)
ROTATION_SEVS = list(HC.ROTATION_DEG)
DEGRADATIONS = {
    "control": {"severities": ["none"], "label": "None (control)"},
    "corrosion": {"severities": CORROSION_SEVS, "label": "Corrosion (ink pits)"},
    "rotation": {"severities": ROTATION_SEVS, "label": "Sheet rotation"},
    "overlay": {"severities": ["light", "heavy"], "families": OVERLAY_FAMS,
                "label": "Overlay (webs / shadows / stripes / darts)"},
    "combined": {"severities": ["mixed"], "label": "Combined (2-3 stacked)"},
}


def item_rng(seed: int, salt: str):
    import hashlib as _h
    import random as _r
    return _r.Random(int.from_bytes(
        _h.sha256(f"captcha-studio:{seed}:{salt}".encode()).digest()[:8], "big"))


def render_one(dtype: str, severity: str, ovl_fam: str, seed: int, salt: str) -> dict:
    """One interactive captcha: base render via the same mechanics the S53
    corpus uses, but driven from (seed, salt) instead of corpus indices."""
    import random  # noqa: F401  (kept near engine calls for parity)

    rng = item_rng(seed, f"{salt}:{dtype}:{severity}:{ovl_fam}")
    label = G.make_label(rng)
    img, font, dx, dy = HC.base_render(rng, label)
    angle = 0.0
    if dtype == "corrosion":
        img = HC.apply_corrosion(img, rng, severity)
    elif dtype == "rotation":
        img, angle = HC.apply_rotation(img, rng, severity)
    elif dtype == "overlay":
        img = HC.apply_overlay(img, rng, ovl_fam, severity)
    elif dtype == "combined":
        picks = rng.sample(["corrosion", "rotation", "spiderweb",
                            "cross-shadow", "strippy", "darts"], rng.randint(2, 3))
        for p in picks:
            if p == "corrosion":
                img = HC.apply_corrosion(img, rng, rng.choice(CORROSION_SEVS))
            elif p == "rotation":
                img, angle = HC.apply_rotation(img, rng, rng.choice(ROTATION_SEVS))
            else:
                img = HC.apply_overlay(img, rng, p, rng.choice(["light", "heavy"]))
        dtype = "combined+" + "+".join(picks)
    # control: untouched
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {
        "png_b64": base64.b64encode(buf.getvalue()).decode(),
        "label": label,
        "degradation_type": dtype,
        "severity": severity,
        "overlay_family": ovl_fam,
        "rotation_deg": round(angle, 2),
        "seed": seed,
        "salt": salt,
        "size": list(img.size),
    }


def ocr_png(png_bytes: bytes) -> dict:
    from PIL import Image
    t0 = time.perf_counter()
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    raw, conf = B.read_text(img, None)
    text = fix_line(raw)
    sec = round(time.perf_counter() - t0, 3)
    return {"text": text, "route": "reader_lex (baseline + lex projection)",
            "reader_ms": round(sec * 1000.0, 1)}


class Handler(BaseHTTPRequestHandler):
    server_version = "captcha-studio/1.0"

    def log_message(self, *a):  # quiet; run.py reports
        pass

    def _json(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/index.html",):
            self.path = "/"
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/":
            return self._file(APP / "static" / "index.html", "text/html; charset=utf-8")
        if path == "/static/app.js":
            return self._file(APP / "static" / "app.js", "text/javascript")
        if path == "/static/style.css":
            return self._file(APP / "static" / "style.css", "text/css")
        if path == "/api/config":
            import PIL, numpy
            try:
                from PIL import features
                freetype = features.version("freetype2") or "present"
            except Exception:
                freetype = "unknown"
            return self._json(200, {
                "ok": True, "app": f"captcha-studio {APP_VERSION}",
                "engine": ENGINE_STAMP,
                "python": sys.version.split()[0],
                "pillow": PIL.__version__, "numpy": numpy.__version__,
                "freetype": freetype,
                "fonts": [FONTS.joinpath(p).name for p in sorted(x.name for x in FONTS.glob("*.ttf"))],
                "degradations": DEGRADATIONS,
            })
        if path == "/api/selftest":
            from selftest import run_selftest
            return self._json(200, run_selftest())
        return self._json(404, {"error": "not-found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad-payload"})
        if path == "/api/generate":
            dtype = str(payload.get("degradation_type", "control"))
            if dtype not in DEGRADATIONS:
                return self._json(400, {"error": "bad-type",
                                        "hint": f"one of {sorted(DEGRADATIONS)}"})
            spec = DEGRADATIONS[dtype]
            sev = str(payload.get("severity", spec["severities"][0]))
            if sev not in spec["severities"]:
                return self._json(400, {"error": "bad-severity",
                                        "hint": f"one of {spec['severities']}"})
            fam = str(payload.get("overlay_family", OVERLAY_FAMS[0]))
            if fam not in OVERLAY_FAMS:
                return self._json(400, {"error": "bad-overlay-family",
                                        "hint": f"one of {OVERLAY_FAMS}"})
            seed = int(payload.get("seed", 1))
            salt = str(payload.get("salt", "studio"))[:64]
            t0 = time.perf_counter()
            try:
                item = render_one(dtype, sev, fam, seed, salt)
            except Exception as e:
                return self._json(500, {"error": "render-failed", "detail": repr(e)})
            item["render_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
            return self._json(200, item)
        if path == "/api/ocr":
            b64 = payload.get("image")
            if not b64:
                return self._json(400, {"error": "bad-payload",
                                        "hint": "send JSON {image: base64-png}"})
            try:
                data = base64.b64decode(b64)
                out = ocr_png(data)
            except Exception as e:
                return self._json(422, {"error": "reader-failed", "detail": repr(e)})
            return self._json(200, out)
        return self._json(404, {"error": "not-found"})


def serve(host: str, port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"captcha-studio serving on http://{host}:{srv.server_address[1]}")
    return srv


def warm_reader():
    """Background CNN/lexicon warmup so the user's first OCR click is fast."""
    import threading
    def _run():
        try:
            it = render_one("control", "none", "spiderweb", 9001, "warmup")
            ocr_png(base64.b64decode(it["png_b64"]))
            print("captcha-studio: reader warm", flush=True)
        except Exception as e:
            print(f"captcha-studio: warmup failed ({e!r}); OCR still works on demand",
                  file=sys.stderr, flush=True)
    threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8433)
    args = ap.parse_args()
    warm_reader()
    serve(args.host, args.port).serve_forever()
