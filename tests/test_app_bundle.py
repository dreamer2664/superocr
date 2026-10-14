#!/usr/bin/env python3
"""Tests for the W2 downloadable app bundle (t-20261013-b411).

Covers the two structural failure modes the bundle exists to kill:
  1. font portability — a machine without the Linux DejaVu system paths must
     fall back to the bundled faces (the historic silent-garbage-read bug);
  2. environment drift — the bundle's --selftest must reproduce the build
     machine's reads EXACTLY via the expected_* manifest fields.

Script-style: run it, exit 0 iff all checks pass. Offline, seeded. The
mini-bundle build keeps this under ~90 s.

    python3 tests/test_app_bundle.py
"""
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name +
          (f"\n      {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


t0 = time.time()

# 1) font fallback: with the system candidates monkeypatched away, the
#    bundled fonts/ dir must supply all 8 faces and rendering must work.
probe = """
import sys
from pathlib import Path
sys.path.insert(0, {root!r})
import generator as G
# simulate a machine with no Linux font tree: every system candidate missing,
# only the bundled fonts/ dir present -> available_fonts() must still yield 8
G._FONT_CANDIDATES = [str(G._LOCAL_FONT_DIR / Path(p).name)
                      for p in G._FONT_CANDIDATES]
faces = G.available_fonts()
assert len(faces) == 8, faces
assert all(str(G._LOCAL_FONT_DIR) in f for f in faces), faces
img, label = G.generate_one("easy", seed=90, index=99)
assert label and img.size == G.DEFAULT_SIZE
print("FALLBACK-OK", label)
""".format(root=str(ROOT))
r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
check("bundled-fonts fallback: 8 faces + generation works with no system fonts",
      r.returncode == 0 and "FALLBACK-OK" in r.stdout,
      f"rc={r.returncode} out={r.stdout.strip()[:120]} err={r.stderr.strip()[-300:]}")

# 2) the committed fonts/ dir is complete (8 ttf + license)
ttfs = sorted((ROOT / "fonts").glob("*.ttf"))
check("fonts/ committed: 8 ttf faces + license",
      len(ttfs) == 8 and (ROOT / "fonts" / "LICENSE-DejaVu.txt").exists(),
      f"{len(ttfs)} ttf files")

# 3) build a mini bundle (2 demo items) and selftest it in-place
tmp = Path(tempfile.mkdtemp(prefix="w2-bundle-test-"))
r = subprocess.run([sys.executable, "app/build_bundle.py",
                    "--out", str(tmp), "--demo-count", "2"],
                   cwd=ROOT, capture_output=True, text=True, timeout=600)
check("mini bundle builds", r.returncode == 0, r.stderr.strip()[-300:])
zips = list(tmp.glob("superocr-app-*.zip"))
bundle_dirs = [p for p in tmp.iterdir() if p.is_dir()]
check("bundle dir + zip produced", len(zips) == 1 and len(bundle_dirs) == 1,
      f"zips={len(zips)} dirs={len(bundle_dirs)}")
if not bundle_dirs:
    print(f"\n{len(failures)} failure(s), {time.time() - t0:.1f}s")
    sys.exit(1)
b = bundle_dirs[0]
for need in ("start.sh", "start.command", "start.bat", "INSTALL.md",
             "requirements.txt", "version.txt", "webapp/server.py",
             "fonts/DejaVuSans.ttf", "demo-suite/easy/manifest.jsonl"):
    check(f"bundle contains {need}", (b / need).exists())
check("version records the exact full source commit",
      json.loads((b / "version.txt").read_text())["git_commit"] ==
      subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
check("launchers are executable",
      os.access(b / "start.sh", os.X_OK) and os.access(b / "start.command", os.X_OK))

r = subprocess.run([sys.executable, "webapp/server.py",
                    "--suites", "demo-suite", "--selftest"],
                   cwd=b, capture_output=True, text=True, timeout=600)
check("bundle selftest PASSes in-place",
      r.returncode == 0 and "-> PASS" in r.stdout,
      f"rc={r.returncode} tail={r.stdout.strip()[-200:]}")
check("selftest reports fonts 8/8", "fonts 8/8" in r.stdout, r.stdout[:120])

# 4) expected-read drift detection actually fails on tampering
man = b / "demo-suite/easy/manifest.jsonl"
original = man.read_text()
row0 = json.loads(original.splitlines()[0])
tampered = dict(row0, expected_lex="deliberately wrong")
man.write_text(json.dumps(tampered) + "\n" +
               "\n".join(original.splitlines()[1:]) + "\n")
r = subprocess.run([sys.executable, "webapp/server.py",
                    "--suites", "demo-suite", "--selftest",
                    "--selftest-limit", "1"],
                   cwd=b, capture_output=True, text=True, timeout=300)
check("tampered expected read -> selftest DRIFT + exit 1",
      r.returncode == 1 and "DRIFT" in r.stdout,
      f"rc={r.returncode} out={r.stdout.strip()[-200:]}")
man.write_text(original)  # restore for the live smoke below

# 5) live server smoke from the bundle: health stamp + lex route read
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p

port = free_port()
proc = subprocess.Popen(
    [sys.executable, "webapp/server.py", "--port", str(port),
     "--host", "127.0.0.1", "--suites", "demo-suite"],
    cwd=b, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    base = f"http://127.0.0.1:{port}"
    up = False
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=2)
            up = True
            break
        except Exception:
            time.sleep(0.5)
    check("bundle server starts and serves /api/health", up)
    if up:
        h = json.load(urllib.request.urlopen(base + "/api/health"))
        check("health carries the bundle stamp + fonts",
              h.get("app_version", {}).get("bundle", "").startswith("superocr-app-")
              and h.get("fonts") == 8,
              json.dumps(h.get("app_version"))[:120])
        img_path = b / "demo-suite/easy/images/easy-0000.png"
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        req = urllib.request.Request(
            base + "/api/ocr",
            data=json.dumps({"image": b64, "route": "lex"}).encode(),
            headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=120))
        check("live /api/ocr lex read matches the build-time expectation",
              d["text"] == row0["expected_lex"] and d["route"] == "lex",
              f"got={d['text']!r} want={row0['expected_lex']!r}")
finally:
    proc.terminate()
    proc.wait(timeout=10)

print(f"\n{len(failures)} failure(s), {time.time() - t0:.1f}s")
sys.exit(1 if failures else 0)
