#!/usr/bin/env python3
"""build_bundle.py — W2 (t-20261013-b411): build the downloadable superocr app.

Carlo's directive (via pericles DM 2026-10-13 15:43): the web app must become
a REAL downloadable standalone application that reliably reads screen
content. Two root causes of "unstable" this bundle fixes structurally:

  1. The demo Carlo watched ran inside an agent sandbox that gets wiped
     regularly — every wipe killed the server mid-demo. The bundle runs on
     CARLO'S machine: nothing to wipe.
  2. "Share screen" called getUserMedia (the CAMERA), not getDisplayMedia —
     the screen button never captured the screen. Fixed in webapp/static/app.js
     on this branch; the bundle carries the fix.

The bundle is generated, never committed (JOBS.md heavy-artefact rule): this
script + the repo are the source of truth; the zip ships as a GitHub Release
asset (--release) or stays local for verification.

    python3 app/build_bundle.py                     # dist/superocr-app-<sha>.zip
    python3 app/build_bundle.py --release           # + upload as Release asset
    python3 app/build_bundle.py --demo-count 4      # fast bundle for tests

What lands in the zip:
    start.sh / start.command / start.bat   launchers (deps check, selftest,
                                           auto-restart watchdog, browser open)
    INSTALL.md                             3-OS install + troubleshooting
    requirements.txt / version.txt         pinned deps / build stamp
    webapp/                                server + UI (screen-read mode)
    baseline.py reader.py generator.py preclassify.py typer.py
    tools/lex_projection.py                the shipping read path
    readers/ models/ recipes/              CNN rerank + weights
    fonts/                                 the 8 DejaVu faces — WITHOUT these
                                           a non-Linux machine silently reads
                                           garbage (available_fonts() -> [])
    demo-suite/                            12 seeded items WITH expected_lex /
                                           expected_typer computed at build
                                           time, so --selftest proves the
                                           install reads identically here
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# everything the read path needs at runtime, repo-relative
COPY_FILES = [
    "baseline.py", "reader.py", "generator.py", "preclassify.py", "typer.py",
    "tools/lex_projection.py",
    "webapp/__init__.py", "webapp/server.py",
    "webapp/static/index.html", "webapp/static/app.js",
    "webapp/static/style.css",
]
COPY_DIRS = ["readers", "models", "recipes", "fonts"]

REQUIREMENTS = """\
# pinned to the range verified by the build machine's receipt; the reader is
# stdlib+numpy+Pillow only (JOBS.md)
numpy>=1.24,<3
Pillow>=9.2,<13
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def build_demo_suite(dst: Path, seed: int, count: int) -> list[dict]:
    """Seeded gallery split easy/hard with build-time expected reads."""
    import generator as G
    import baseline as B
    import typer as T
    sys.path.insert(0, str(ROOT / "tools"))
    from lex_projection import fix_line
    from PIL import Image  # noqa: F401  (keep import order stable)

    picks = (["easy"] * max(1, count // 2) +
             ["collage", "corrosion", "spiderweb"] * count)[:count]
    rows = []
    for i, fam in enumerate(picks):
        split = "easy" if fam == "easy" else "hard"
        img, label = G.generate_one(fam, seed=seed, index=i)
        d = dst / split
        (d / "images").mkdir(parents=True, exist_ok=True)
        name = f"{fam}-{i:04d}.png"
        img.save(d / "images" / name)
        # the two reads exactly as the server's routes compute them
        text_raw, _ = B.read_text(img, None)
        expected_lex = fix_line(text_raw)
        expected_typer, _, _ = T.recognise(img, "auto")
        rows.append((split, {
            "id": f"{split}-{i:04d}", "image": f"images/{name}",
            "label": label, "family": fam,
            "tags": ["demo", f"seed={seed}"],
            "expected_lex": expected_lex, "expected_typer": expected_typer,
        }))
    for split in ("easy", "hard"):
        lines = [json.dumps(r) for s, r in rows if s == split]
        if lines:
            (dst / split / "manifest.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8")
    return [r for _, r in rows]


LAUNCHER_SH = """\
#!/bin/sh
# superocr app launcher (macOS / Linux). Ctrl-C or close the window to stop.
set -e
cd "$(dirname "$0")"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "ERROR: python not found. Install Python 3.11+ from https://python.org and re-run."
  exit 1
fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "ERROR: python too old ($("$PY" -V 2>&1)). Need 3.9+, recommend 3.11+."
  exit 1
}
if ! "$PY" -c "import numpy, PIL" >/dev/null 2>&1; then
  echo "First run: installing dependencies (numpy, Pillow)…"
  "$PY" -m pip install --user -r requirements.txt \\
    || "$PY" -m pip install -r requirements.txt
fi
PORT="${SUPEROOCR_PORT:-8477}"
if [ "$1" != "--no-selftest" ]; then
  echo "Self-test (first run builds the template cache, ~1 min)…"
  # POSIX sh has no portable pipefail: piping Python into tee loses its
  # status. Capture it before logging; keep the existing warn-and-start policy.
  selftest_status=0
  selftest_output=$("$PY" webapp/server.py --suites demo-suite --selftest 2>&1) \\
    || selftest_status=$?
  printf '%s\\n' "$selftest_output" | tee -a app.log
  if [ "$selftest_status" -ne 0 ]; then
    echo "SELF-TEST FAILED — details above and in app.log."
    echo "Starting anyway; reads may be WRONG until this is fixed (see INSTALL.md)."
  fi
fi
echo "superocr starting on http://127.0.0.1:$PORT — keep this window open."
OPEN="--open"
while true; do
  set +e
  "$PY" webapp/server.py --port "$PORT" --host 127.0.0.1 \\
      --suites demo-suite $OPEN
  code=$?
  set -e
  OPEN=""
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) server exited code=$code" >> app.log
  [ "$code" -eq 0 ] && break
  echo "server crashed (exit $code) — restarting in 2s (see app.log)"
  sleep 2
done
"""

LAUNCHER_BAT = """\
@echo off
rem superocr app launcher (Windows). Close this window to stop.
setlocal
cd /d "%~dp0"
set PORT=8477
if defined SUPEROOCR_PORT set PORT=%SUPEROOCR_PORT%
where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found. Install Python 3.11+ from https://python.org
  echo ^(installer: tick "Add python.exe to PATH"^), then re-run.
  pause
  exit /b 1
)
python -c "import numpy, PIL" >nul 2>&1
if errorlevel 1 (
  echo First run: installing dependencies ^(numpy, Pillow^)...
  python -m pip install --user -r requirements.txt || python -m pip install -r requirements.txt
)
if not "%1"=="--no-selftest" (
  echo Self-test ^(first run builds the template cache, ~1 min^)...
  python webapp\\server.py --suites demo-suite --selftest >> app.log 2>&1
  type app.log
  if errorlevel 1 echo SELF-TEST FAILED - see app.log and INSTALL.md. Starting anyway.
)
echo superocr starting on http://127.0.0.1:%PORT% - keep this window open.
set OPEN=--open
:loop
python webapp\\server.py --port %PORT% --host 127.0.0.1 --suites demo-suite %OPEN%
set OPEN=
echo %date% %time% server exited >> app.log
timeout /t 2 /nobreak >nul
goto loop
"""

INSTALL_MD = """\
# superocr — downloadable app

Reads text from your screen (or from image files) using the superocr reader.
Everything runs **locally**: no account, no network calls from the app, no
image ever leaves your machine. (Internet is needed once, on first start, to
install the two Python dependencies.)

## Requirements

- Python **3.9+** (3.11+ recommended) — https://python.org
  - Windows: in the installer, tick **"Add python.exe to PATH"**.
- ~120 MB disk.

## Start

| OS | do this |
|---|---|
| **macOS** | double-click `start.command` (first time: right-click → Open, to pass Gatekeeper). Grant the **Screen Recording** permission when macOS asks, then re-run. |
| **Windows** | double-click `start.bat`. |
| **Linux** | `./start.sh` in a terminal. |

First start runs a **self-test** (~1 minute: it builds a template cache, then
reads the 12 bundled demo images and verifies the reads match the build
machine exactly). Then your browser opens at `http://127.0.0.1:8477`.
Keep the launcher window open while using the app; close it to quit.
If the app ever crashes, the launcher restarts it automatically and appends
to `app.log` — include that file when reporting a problem.

## Reading your screen

1. **Live OCR** tab → **Share screen**.
2. Your browser asks what to share: the whole screen, one window, or a tab.
   Pick one → **Share**.
3. The live feed appears. Optional: **drag a rectangle** on the feed to read
   only that region.
4. **Read now** for one read, or set the **auto interval** for continuous
   reads. Switch **Route** to `lex` for the shipping reader (slower, ~2 s,
   more accurate on rendered text); `typer` is the fast demo route.

Files work too: drop an image anywhere on the drop zone.

## What it reads well (honesty section)

superocr is built and measured on **rendered CAPTCHA-style text** (words from
a fixed vocabulary, DejaVu fonts, degraded backgrounds). On that material the
shipping route measures **easy 73/100, hard 23/100 exact-phrase** on the
canonical 100-item suites, ~2.1 s per image median. The bar (98/95) is NOT
met — this app is a demo of the current state, not a finished product.
Arbitrary screen text (small UI labels, non-DejaVu fonts, rich layouts) is
out of distribution: expect misses. The header chip shows `fonts 8/8` when
the bundled faces loaded; **`fonts 0/8` means reads are garbage** — see
troubleshooting.

## Troubleshooting

- **`fonts 0/8` (red header) or selftest DRIFT lines** — the `fonts/` folder
  is missing or moved. Restore the bundle (unzip again); do not rename dirs.
- **Share screen does nothing / NotAllowedError** — the page must be opened
  via `http://127.0.0.1:8477` (the launcher does this). A LAN IP or `file://`
  is not a secure context and browsers block capture there. macOS: System
  Settings → Privacy & Security → Screen Recording → enable your browser.
- **Port busy** — run with `SUPEROOCR_PORT=8501 ./start.sh` (or edit
  `set PORT` in `start.bat`).
- **Self-test fails on first run only, then passes** — normal: the first run
  builds `.template-cache/` (a few seconds longer).
- **App misbehaves** — open `app.log` (crash traces land there), and report
  the `bundle` stamp shown in the page header (e.g. `bundle superocr-app-abc123`).

## Uninstall

Delete the folder. Nothing is written outside it (except pip's `--user`
dependency install on first run).

## Provenance

Built from dreamer2664/superocr — see `version.txt` for the exact commit and
build time. DejaVu fonts are redistributed under their free license
(`fonts/LICENSE-DejaVu.txt`).
"""


def build(outdir: Path, demo_count: int, seed: int) -> Path:
    sha = git_sha()
    bundle_name = f"superocr-app-{sha}"
    stage = outdir / bundle_name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for rel in COPY_FILES:
        src, dst = ROOT / rel, stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for d in COPY_DIRS:
        shutil.copytree(ROOT / d, stage / d,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    (stage / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (stage / "INSTALL.md").write_text(INSTALL_MD, encoding="utf-8")
    (stage / "start.sh").write_text(LAUNCHER_SH, encoding="utf-8", newline="\n")
    (stage / "start.command").write_text(LAUNCHER_SH, encoding="utf-8", newline="\n")
    (stage / "start.bat").write_text(LAUNCHER_BAT, encoding="utf-8", newline="\r\n")
    os.chmod(stage / "start.sh", 0o755)
    os.chmod(stage / "start.command", 0o755)

    rows = build_demo_suite(stage / "demo-suite", seed, demo_count)

    version = {
        "bundle": bundle_name,
        "git_commit": sha,
        "built_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "demo_items": len(rows),
        "demo_seed": seed,
    }
    (stage / "version.txt").write_text(json.dumps(version, indent=2),
                                       encoding="utf-8")

    zip_path = outdir / f"{bundle_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(outdir))
    return zip_path


def release(zip_path: Path, token: str) -> str:
    import urllib.request
    sha = git_sha()
    tag = f"app-v0.1.0-{sha}"
    body = json.dumps({
        "tag_name": tag,
        "name": f"superocr app 0.1.0 ({sha})",
        "body": ("Downloadable standalone superocr app (W2, t-20261013-b411): "
                 "screen-read mode via getDisplayMedia, bundled DejaVu faces, "
                 "self-test with build-time expected reads, auto-restart "
                 "launcher. See INSTALL.md inside. Build provenance in "
                 "version.txt."),
        "draft": False, "prerelease": True,
    }).encode()
    req = urllib.request.Request(
        "https://api.github.com/repos/dreamer2664/superocr/releases",
        data=body, method="POST",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as r:
        rel = json.load(r)
    upload = rel["upload_url"].split("{")[0]
    data = zip_path.read_bytes()
    req = urllib.request.Request(
        f"{upload}?name={zip_path.name}", data=data, method="POST",
        headers={"Authorization": f"token {token}",
                 "Content-Type": "application/zip"})
    with urllib.request.urlopen(req) as r:
        asset = json.load(r)
    return f"{rel['html_url']} (asset: {asset['name']} {asset['size']}B)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="dist")
    ap.add_argument("--demo-count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=90)
    ap.add_argument("--release", action="store_true",
                    help="upload the zip as a GitHub Release asset "
                         "(token from GITHUB_TOKEN/CHATCODE_TOKEN env)")
    args = ap.parse_args()

    outdir = (ROOT / args.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    zip_path = build(outdir, args.demo_count, args.seed)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print(f"built {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB) "
          f"in {time.perf_counter() - t0:.1f}s")
    print(f"zip sha256: {digest}")
    if args.release:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("CHATCODE_TOKEN")
        if not token:
            print("ERROR: --release needs GITHUB_TOKEN or CHATCODE_TOKEN in env")
            return 1
        print("release:", release(zip_path, token))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
