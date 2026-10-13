#!/usr/bin/env python3
"""superocr web app — browser dashboard + screen-overlay OCR (t-20261013-c395).

Carlo's directive: a web app for superocr that acts as an overlay reading the
screen, replacing the terminal. Extends the S4 demo (tools/demo_server.py)
into a full single-page UI. Same honesty rules as the demo:

- OCR goes through the SAME shared path as the CLI (typer.recognise ->
  reader.read_chain). The web app is a window on the pipeline, not a
  parallel implementation.
- Every /api/ocr response carries server_ms, measured around the recognise()
  call alone.
- stdlib + numpy/Pillow only; no CDN, no frameworks, no network calls from
  the page. Works from a clean clone with `python3 webapp/server.py`.

Endpoints
    GET  /                     single-page app (webapp/static/)
    GET  /static/<file>        app.js, style.css
    GET  /api/health           liveness + build info (git sha, models)
    POST /api/ocr              {image: base64, family?: str, detail?: bool}
    GET  /api/suites           suite dirs passed via --suites (comma sep)
    GET  /api/suite-items      ?suite=&split=  (id/label/family list)
    GET  /api/suite-image      ?suite=&split=&id=  (png bytes + label header)
    GET  /api/reports          bench receipt summaries from reports/
    GET  /api/report           ?file=  raw receipt JSON
    GET  /api/bus              ?channel=&limit=  (needs --bus-dir)
    GET  /api/tasks            board task list (needs --board-dir)

Usage:
    python3 webapp/server.py [--port 8421] [--host 0.0.0.0]
        [--suites /path/suiteA,/path/suiteB]
        [--bus-dir /path/chatcode/bus] [--board-dir /path/chatcode/board/tasks]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import typer as T  # noqa: E402  (imports generator + reader via it)
import baseline as B  # noqa: E402  (the shipping floor: read_text)
import generator as G  # noqa: E402  (W2: font-face diagnostics + selftest gen)

sys.path.insert(0, str(ROOT / "tools"))
from lex_projection import fix_line  # noqa: E402  (shipping post-pass)

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD = 4 * 1024 * 1024  # 4 MiB, same as the S4 demo
MAX_BUS_LINES = 500
VERSION = "1.0"

# Configured at startup (CLI args); read-only afterwards.
CONFIG: dict = {"suites": [], "bus_dir": None, "board_dir": None}


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _app_version() -> dict | None:
    """W2: the downloadable bundle ships a version.txt stamp (build sha,
    build time, bundle id). In-repo runs have none — returns None."""
    p = ROOT / "version.txt"
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        return {"raw": p.read_text()[:200]}
    return None


def _crash_log(where: str, exc: BaseException):
    """W2: every uncaught exception gets a timestamped line in app.log next
    to the server root, so 'it broke' becomes diagnosable after the fact."""
    import traceback
    try:
        with open(ROOT / "app.log", "a", encoding="utf-8") as fh:
            fh.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%S')} {where} ===\n")
            fh.write("".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__)))
    except Exception:
        pass  # logging must never be the thing that kills the server


def build_info() -> dict:
    models = {}
    for p in sorted((ROOT / "models").glob("*.npz")):
        models[p.name] = p.stat().st_size
    return {
        "ok": True,
        "version": VERSION,
        "app_version": _app_version(),  # W2: bundle stamp (None in-repo)
        "git_commit": _git_sha(),
        "python": sys.version.split()[0],
        "models": models,
        # W2: font faces are load-bearing — with 0 faces the reader silently
        # degrades to Pillow's bitmap default and reads turn to garbage, so
        # health surfaces the count and selftest fails loudly below 8.
        "fonts": len(G.available_fonts()),
        "suites_configured": [s["name"] for s in CONFIG["suites"]],
        "bus_enabled": CONFIG["bus_dir"] is not None,
        "board_enabled": CONFIG["board_dir"] is not None,
    }


# ---------------------------------------------------------------- suites

def scan_suites() -> list[dict]:
    out = []
    for entry in CONFIG["suites"]:
        info = {"name": entry["name"], "path": str(entry["path"]), "splits": {}}
        for split_dir in sorted(entry["path"].iterdir()):
            manifest = split_dir / "manifest.jsonl"
            if not split_dir.is_dir() or not manifest.exists():
                continue
            fams: dict[str, int] = {}
            n = 0
            for line in manifest.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n += 1
                fams[item.get("family", "?")] = fams.get(item.get("family", "?"), 0) + 1
            info["splits"][split_dir.name] = {"total": n, "families": fams}
        out.append(info)
    return out


def list_suite_items(suite: str, split: str, limit: int = 500) -> list[dict]:
    for entry in CONFIG["suites"]:
        if entry["name"] != suite:
            continue
        manifest = entry["path"] / split / "manifest.jsonl"
        if not manifest.exists():
            return []
        items = []
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                it = json.loads(line)
            except json.JSONDecodeError:
                continue
            items.append({"id": it.get("id", ""), "label": it.get("label", ""),
                          "family": it.get("family", "?")})
            if len(items) >= limit:
                break
        return items
    return []


def find_suite_item(suite: str, split: str, item_id: str):
    for entry in CONFIG["suites"]:
        if entry["name"] != suite:
            continue
        manifest = entry["path"] / split / "manifest.jsonl"
        if not manifest.exists():
            return None
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("id") == item_id:
                img = (entry["path"] / split / item["image"]).resolve()
                # path-traversal guard: resolved image must stay in the suite
                if not img.is_relative_to(entry["path"].resolve()):
                    return None
                if not img.exists():
                    return None
                return img, item
    return None


# ---------------------------------------------------------------- reports

def scan_reports(limit: int = 200) -> list[dict]:
    rows = []
    rdir = ROOT / "reports"
    if not rdir.exists():
        return rows
    for p in sorted(rdir.glob("*.json"), reverse=True)[:limit]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "bench" not in d:
            continue  # not a bench receipt
        suites = d.get("suites", {})
        row = {
            "file": p.name,
            "run_id": d.get("run_id", p.stem),
            "started_ts": d.get("started_ts", ""),
            "seed": d.get("seed"),
            "reader": (d.get("reader") or {}).get("name", "?"),
            "git_commit": (d.get("git_commit") or "")[:8],
            "totals": d.get("totals", {}),
            "passed": d.get("passed"),
            "splits": {},
        }
        for name, s in suites.items():
            if isinstance(s, dict):
                row["splits"][name] = {
                    "correct": s.get("correct"), "total": s.get("total"),
                    "bar": s.get("bar"), "passed": s.get("passed"),
                    "median_s": s.get("median_s"),
                }
        rows.append(row)
    return rows


def read_report(fname: str):
    p = (ROOT / "reports" / fname).resolve()
    if not p.is_relative_to((ROOT / "reports").resolve()) or not p.exists():
        return None
    if p.suffix == ".json":
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return {"text": p.read_text(encoding="utf-8")[:200_000]}


# ---------------------------------------------------------------- bus/board

def read_bus(channel: str, limit: int) -> dict:
    bus_dir = CONFIG["bus_dir"]
    if bus_dir is None:
        return {"enabled": False,
                "hint": "start the server with --bus-dir <chatcode/bus>"}
    safe = channel.replace("/", "_").replace("..", "_")
    p = bus_dir / f"{safe}.jsonl"
    channels = sorted(f.stem for f in bus_dir.glob("*.jsonl"))
    if not p.exists():
        return {"enabled": True, "channel": channel, "channels": channels,
                "messages": [], "error": "channel-not-found"}
    msgs = []
    lines = p.read_text(encoding="utf-8").splitlines()
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        msgs.append({k: m.get(k) for k in ("ts", "from", "type", "text", "ref")})
    return {"enabled": True, "channel": channel, "channels": channels,
            "total": len(lines), "messages": msgs}


def read_tasks() -> dict:
    board = CONFIG["board_dir"]
    if board is None:
        return {"enabled": False,
                "hint": "start the server with --board-dir <chatcode/board/tasks>"}
    tasks = []
    for p in sorted(board.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        tasks.append({
            "id": d.get("id", p.stem), "title": d.get("title", ""),
            "status": d.get("status", "?"), "owner": d.get("owner"),
            "pr": d.get("pr"), "priority": d.get("priority"),
            "updated_ts": d.get("updated_ts", ""),
        })
    by_status: dict[str, int] = {}
    for t in tasks:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    return {"enabled": True, "total": len(tasks), "by_status": by_status,
            "tasks": sorted(tasks, key=lambda t: t["updated_ts"], reverse=True)}


# ---------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    server_version = f"superocr-webapp/{VERSION}"

    def log_message(self, fmt, *args):  # keep stdout readable
        pass

    def _json(self, code: int, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)
        try:
            self._route_get(path, qs)
        except BrokenPipeError:
            pass
        except Exception as e:  # the server never dies on one bad request
            _crash_log(f"GET {path}", e)
            try:
                self._json(500, {"error": "internal", "detail": repr(e)})
            except Exception:
                pass

    def _route_get(self, path: str, qs: dict):
        if path in ("/", "/index.html"):
            body = (STATIC / "index.html").read_bytes()
            return self._bytes(200, body, "text/html; charset=utf-8")
        if path.startswith("/static/"):
            name = Path(path[len("/static/"):]).name  # no traversal
            p = STATIC / name
            if not p.exists() or p.suffix not in (".js", ".css", ".svg", ".png"):
                return self._json(404, {"error": "not-found"})
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            return self._bytes(200, p.read_bytes(), ctype)
        if path == "/api/health":
            return self._json(200, build_info())
        if path == "/api/suites":
            return self._json(200, {"suites": scan_suites()})
        if path == "/api/suite-items":
            suite = (qs.get("suite") or [""])[0]
            split = (qs.get("split") or [""])[0]
            return self._json(200, {"suite": suite, "split": split,
                                    "items": list_suite_items(suite, split)})
        if path == "/api/suite-image":
            suite = (qs.get("suite") or [""])[0]
            split = (qs.get("split") or [""])[0]
            item_id = (qs.get("id") or [""])[0]
            found = find_suite_item(suite, split, item_id)
            if found is None:
                return self._json(404, {"error": "item-not-found"})
            img, item = found
            return self._bytes(200, img.read_bytes(),
                               mimetypes.guess_type(str(img))[0] or "image/png",
                               {"X-Item-Label": item.get("label", ""),
                                "X-Item-Family": item.get("family", ""),
                                "Access-Control-Expose-Headers":
                                    "X-Item-Label, X-Item-Family"})
        if path == "/api/reports":
            return self._json(200, {"reports": scan_reports()})
        if path == "/api/report":
            fname = (qs.get("file") or [""])[0]
            d = read_report(fname)
            if d is None:
                return self._json(404, {"error": "report-not-found"})
            return self._json(200, d)
        if path == "/api/bus":
            channel = (qs.get("channel") or ["general"])[0]
            limit = min(int((qs.get("limit") or ["100"])[0]), MAX_BUS_LINES)
            return self._json(200, read_bus(channel, limit))
        if path == "/api/tasks":
            return self._json(200, read_tasks())
        return self._json(404, {"error": "not-found"})

    # ------------------------------------------------------------ POST
    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/ocr":
            return self._json(404, {"error": "not-found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            # drain (bounded) so the client gets a clean 413, not a reset
            remaining = min(length, MAX_UPLOAD * 2)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            return self._json(413, {"error": "upload-empty-or-too-large",
                                    "limit_bytes": MAX_UPLOAD})
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
            data = base64.b64decode(payload["image"])
            family = str(payload.get("family", "auto"))
            detail = bool(payload.get("detail", False))
            route = str(payload.get("route", "typer"))
        except Exception:
            return self._json(400, {"error": "bad-payload",
                                    "hint": "send JSON {image: base64, family?: str, route?: str}"})
        if route not in ("typer", "lex"):
            return self._json(400, {"error": "bad-route",
                                    "hint": "route must be 'typer' or 'lex'"})
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            return self._json(400, {"error": "not-an-image"})
        t0 = time.perf_counter()
        try:
            if route == "lex":
                # the SHIPPING bench route: reader_lex == baseline.read_text
                # (family=None, the measured 73/21 floor) + lex_projection
                # .fix_line. family is ignored on purpose — the bench runs
                # bare `python3 baseline.py {image}`, and the receipt numbers
                # are bound to exactly that call.
                text_raw, conf = B.read_text(img, None)
                text = fix_line(text_raw)
                fam = "floor+lex"
            else:
                text, conf, fam = T.recognise(img, family)
                text_raw = None
        except SystemExit as e:  # reader dies honestly; so do we
            return self._json(422, {"error": "reader-refused", "detail": str(e)})
        except Exception as e:
            _crash_log(f"POST /api/ocr route={route}", e)
            return self._json(500, {"error": "reader-failed", "detail": repr(e)})
        server_ms = (time.perf_counter() - t0) * 1000.0
        avg = round(sum(conf) / len(conf), 3) if conf else 0.0
        out = {"text": text, "family": fam, "avg_confidence": avg,
               "server_ms": round(server_ms, 1), "route": route}
        if text_raw is not None and text_raw != text:
            out["text_raw"] = text_raw
        if detail:
            out["confidences"] = [round(c, 4) for c in conf]
        return self._json(200, out)


def serve(host: str, port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), Handler)
    return srv


# ---------------------------------------------------------------- selftest
def run_selftest(limit_per_split: int = 999) -> int:
    """W2 (t-20261013-b411): the loud startup check for the downloadable app.

    Runs every configured-suite item through BOTH ocr routes. If the manifest
    carries `expected_lex`/`expected_typer` (the app bundle does — computed at
    build time on the verified machine), the read must reproduce EXACTLY, so
    any environment drift (missing fonts being the historic killer: 0 faces
    silently degrades to Pillow's bitmap default) becomes a named FAIL line
    instead of mystery garbage reads later. Without expectations (plain repo
    suites) it degrades to a machinery check: every item must run clean.
    Returns a process exit code: 0 = healthy, 1 = drift/breakage.
    """
    faces = G.available_fonts()
    print(f"selftest: python {sys.version.split()[0]} · fonts {len(faces)}/8 · "
          f"suites {[s['name'] for s in CONFIG['suites']]}")
    if len(faces) < 8:
        print("FAIL  font faces missing — reads would silently degrade to "
              "Pillow's bitmap default. Reinstall the bundle (fonts/ dir).")
        return 1
    bad = 0
    ran = 0
    for entry in CONFIG["suites"]:
        for split_dir in sorted(p for p in entry["path"].iterdir() if p.is_dir()):
            manifest = split_dir / "manifest.jsonl"
            if not manifest.exists():
                continue
            n = 0
            for line in manifest.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or n >= limit_per_split:
                    continue
                it = json.loads(line)
                n += 1
                ran += 1
                img_path = split_dir / it.get("image", "")
                label = it.get("label", "")
                try:
                    img = Image.open(img_path).convert("RGB")
                except Exception as e:
                    print(f"FAIL  {it.get('id')}: cannot open {img_path}: {e!r}")
                    bad += 1
                    continue
                try:
                    t0 = time.perf_counter()
                    text_raw, _ = B.read_text(img, None)
                    lex = fix_line(text_raw)
                    lex_ms = (time.perf_counter() - t0) * 1000.0
                except Exception as e:
                    print(f"FAIL  {it.get('id')}: lex route raised {e!r}")
                    bad += 1
                    continue
                try:
                    typ, _, _ = T.recognise(img, "auto")
                except Exception as e:
                    print(f"FAIL  {it.get('id')}: typer route raised {e!r}")
                    bad += 1
                    continue
                drift = []
                if "expected_lex" in it and it["expected_lex"] != lex:
                    drift.append(f"lex {it['expected_lex']!r} -> {lex!r}")
                if "expected_typer" in it and it["expected_typer"] != typ:
                    drift.append(f"typer {it['expected_typer']!r} -> {typ!r}")
                hit = "exact" if lex == label else "miss"
                if drift:
                    bad += 1
                    print(f"DRIFT {it.get('id')} [{hit} {lex_ms:.0f}ms]: "
                          + "; ".join(drift))
                else:
                    print(f"ok    {it.get('id')} [{hit}] lex={lex!r} "
                          f"({lex_ms:.0f}ms)")
    print(f"selftest: {ran} items, {bad} failure(s) -> "
          + ("PASS" if bad == 0 and ran > 0 else "FAIL" if bad else "EMPTY"))
    return 0 if (bad == 0 and ran > 0) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8421)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--suites", default="",
                    help="comma-separated suite dirs (each holding split/manifest.jsonl)")
    ap.add_argument("--bus-dir", default="",
                    help="chatcode bus dir (jsonl channels) for the bus viewer")
    ap.add_argument("--board-dir", default="",
                    help="chatcode board/tasks dir for the task feed")
    ap.add_argument("--selftest", action="store_true",
                    help="W2: run both ocr routes over the configured suites, "
                         "compare against expected_* manifest fields, then exit")
    ap.add_argument("--selftest-limit", type=int, default=999,
                    help="max items per split in --selftest")
    ap.add_argument("--open", action="store_true",
                    help="W2: open the app in the default browser once bound")
    args = ap.parse_args()

    for d in filter(None, (s.strip() for s in args.suites.split(","))):
        p = Path(d).expanduser().resolve()
        if p.is_dir():
            CONFIG["suites"].append({"name": p.name, "path": p})
        else:
            print(f"warn: suite dir not found, skipping: {p}", file=sys.stderr)
    if args.bus_dir:
        p = Path(args.bus_dir).expanduser().resolve()
        CONFIG["bus_dir"] = p if p.is_dir() else None
        if CONFIG["bus_dir"] is None:
            print(f"warn: bus dir not found: {p}", file=sys.stderr)
    if args.board_dir:
        p = Path(args.board_dir).expanduser().resolve()
        CONFIG["board_dir"] = p if p.is_dir() else None
        if CONFIG["board_dir"] is None:
            print(f"warn: board dir not found: {p}", file=sys.stderr)

    if args.selftest:
        raise SystemExit(run_selftest(args.selftest_limit))

    srv = serve(args.host, args.port)
    print(f"superocr webapp on http://{args.host}:{args.port} — "
          f"suites={len(CONFIG['suites'])} bus={'on' if CONFIG['bus_dir'] else 'off'} "
          f"board={'on' if CONFIG['board_dir'] else 'off'} — Ctrl-C to stop")
    if args.open:
        import threading
        import webbrowser
        url = f"http://127.0.0.1:{args.port}"
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        print(f"opening {url} in your browser…")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
