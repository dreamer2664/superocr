#!/usr/bin/env python3
"""Build the qcaptcha Screen Solver bundle from an explicit file allowlist.

Self-contained: a stranger unzips, runs start.*, calibrates twice, arms — no
superocr checkout needed. The bundle carries the shipping reader (classic
floor + lex projection), the seven weight files, the DejaVu faces and a
generator font-fallback patch identical in effect to W2 PR #82 (t-20261013-
b411): system fonts always win; bundled fonts are the fallback on machines
with no Linux font tree, so reads behave identically there.

Never copied: datasets, credentials, reports, hidden files, venvs, caches.

Font provenance: this repo tree has no fonts/ yet (both W2 #82 and G1 #84 are
open PRs that add the same eight faces). Order of sourcing:
  1. <root>/fonts/                       (W2 tree once merged)
  2. <root>/apps/captcha-studio/fonts/   (G1 tree once merged)
  3. git show <font_ref>:apps/captcha-studio/fonts/<name>   (unmerged source;
     recorded in MANIFEST.json as font_source for full honesty)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps" / "qcaptcha"
FONT_REF = "refs/tmp/pr84"  # fetched via: git fetch origin '+refs/pull/84/head:refs/tmp/pr84'

ENGINE_FILES = [
    "baseline.py", "reader.py", "preclassify.py", "generator.py",
    "tools/lex_projection.py",
    "readers/segmentation.py", "readers/glyphcnn.py", "readers/piece_cnn.py",
    "recipes/glyphcnn.json", "recipes/glyphcnn-v3.json", "recipes/glyphcnn-v4.json",
    "recipes/glyphcnn-v7.json", "recipes/glyphcnn-v7b.json",
    "models/glyphcnn.npz", "models/glyphcnn-v2.npz", "models/glyphcnn-v3.npz",
    "models/glyphcnn-v4.npz", "models/glyphcnn-v7.npz", "models/glyphcnn-v7b.npz",
    "models/preclass_centroids.npz",
]
APP_FILES = [
    "qcaptcha/__init__.py", "qcaptcha/config.py", "qcaptcha/capture.py",
    "qcaptcha/injection.py", "qcaptcha/engine.py", "qcaptcha/solver.py",
    "qcaptcha/overlay.py", "qcaptcha/gemini.py", "qcaptcha/readers.py",
    "qcaptcha/phone.py",
    "launcher.py", "README.md", "PHONE.md", "requirements.txt",
]
FONT_NAMES = [
    "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf",
    "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf",
    "DejaVuSansMono-Oblique.ttf", "DejaVuSansMono-BoldOblique.ttf",
    "LICENSE_DEJAVU.txt", "SHA256SUMS.json",
]
PATCH_MARKER = "qcaptcha bundle font fallback"
FONT_PATCH = f'''
# ---- {PATCH_MARKER} (mirrors W2 PR #82 t-20261013-b411) ----
# Bundled fonts are the FALLBACK; the system copy always wins when present.
_LOCAL_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_FONT_CANDIDATES = _FONT_CANDIDATES + [
    str(_LOCAL_FONT_DIR / Path(_p).name) for _p in list(_FONT_CANDIDATES)
    if str(_p).startswith("/usr/")]


def available_fonts() -> list[str]:  # noqa: F811 — one entry per face, system preferred
    out, seen = [], set()
    for p in _FONT_CANDIDATES:
        name = Path(p).name
        if name not in seen and Path(p).exists():
            seen.add(name)
            out.append(p)
    return out
'''
SH = '''#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "Python 3.10+ is required. See README.md."; exit 1; fi
exec "$PY" launch.py "$@"
'''
BAT = '''@echo off\r
cd /d "%~dp0"\r
where py >nul 2>nul\r
if %errorlevel% equ 0 (\r
  py -3 launch.py %*\r
) else (\r
  python launch.py %*\r
)\r
set "SOLVER_EXIT=%errorlevel%"\r
if not "%SOLVER_EXIT%"=="0" (\r
  echo qcaptcha stopped with an error. See README.md.\r
  pause\r
)\r
exit /b %SOLVER_EXIT%\r
'''


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), *args],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "this source tree has no usable git (revision/dirty checks need it). "
            "Restore the checkout, or set QCAPTCHA_BUILD_REV=<40-hex> to build a "
            "development bundle without git provenance") from e


def _font_source(target: Path, name: str, out_dir: Path) -> str:
    """Find a font/license file, copy it, return its provenance string."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for candidate, tag in ((ROOT / "fonts" / name, "tree:fonts/"),
                           (ROOT / "apps" / "captcha-studio" / "fonts" / name,
                            "tree:apps/captcha-studio/fonts/")):
        if candidate.is_file():
            shutil.copyfile(candidate, target)
            return tag + name
    # unmerged fallback: read from git objects
    src = f"apps/captcha-studio/fonts/{name}"
    try:
        data = subprocess.check_output(["git", "-C", str(ROOT), "show",
                                        f"{FONT_REF}:{src}"])
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"font {name} not in tree and not readable from {FONT_REF}:{src} — "
            f"fetch it first: git fetch origin '+refs/pull/84/head:{FONT_REF}'"
        ) from e
    target.write_bytes(data)
    return f"{FONT_REF}:{src} (unmerged source — becomes tree: after #84/#82 merges)"


def build(output: Path, allow_dirty: bool = False) -> dict:
    try:
        revision = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain"))
        revision_source = "git"
    except RuntimeError:
        env_rev = os.environ.get("QCAPTCHA_BUILD_REV", "").strip()
        if not env_rev:
            raise
        revision, dirty, revision_source = env_rev, True, "env (no git — development build)"
        allow_dirty = True
    if dirty and not allow_dirty:
        raise RuntimeError("commit the source before a release build "
                           "(or use --allow-dirty for a development build)")
    stamp = revision[:12] + ("-dev" if dirty else "")
    name = "qcaptcha-solver-" + stamp
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    directory = output / name
    if directory.exists():
        raise RuntimeError("output directory already exists; choose a fresh --out directory")
    directory.mkdir()

    copies: list[tuple[Path, str]] = []
    for rel in ENGINE_FILES:
        copies.append((ROOT / rel, rel))
    for rel in APP_FILES:
        if rel == "launcher.py":
            copies.append((APP / rel, "launch.py"))  # root entry point
        elif rel.startswith("qcaptcha/"):
            copies.append((APP / rel, rel))          # the package keeps its path
        else:
            copies.append((APP / rel, rel))
    for source, target in copies:
        if not source.is_file() or source.is_symlink():
            raise RuntimeError("missing/unsafe allowlisted input: " + str(source))
        dest = directory / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)

    # generator font fallback patch (idempotent)
    gen_path = directory / "generator.py"
    text = gen_path.read_text()
    patched = False
    if PATCH_MARKER not in text:
        gen_path.write_text(text.rstrip("\n") + "\n" + FONT_PATCH)
        patched = True

    # fonts
    font_sources = {(directory / "fonts" / n): _font_source(directory / "fonts" / n, n, directory)
                    for n in FONT_NAMES}

    # launcher scripts
    (directory / "start.sh").write_text(SH, encoding="utf-8")
    (directory / "start.command").write_text(SH, encoding="utf-8")
    (directory / "start.bat").write_bytes(BAT.encode("utf-8"))
    for f in ("start.sh", "start.command"):
        (directory / f).chmod(0o755)

    hashes = {str(p.relative_to(directory)).replace("\\", "/"):
              hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(directory.rglob("*")) if p.is_file()}
    info = {
        "product": "qcaptcha — superocr Screen Solver",
        "recipe": "qcaptcha-solver-v1",
        "revision": revision, "revision_source": revision_source,
        "dirty": dirty, "clean_source": not dirty,
        "release": not dirty and not any("unmerged" in v for v in font_sources.values()),
        "reader_route": "baseline.read_text(img, None) + tools/lex_projection.fix_line "
                        "(shipping lex route; same call as webapp /api/ocr route=lex)",
        "fonts": {n: font_sources[directory / "fonts" / n] for n in FONT_NAMES},
        "generator_font_fallback_patched": patched,
        "accuracy_target_met": False,
        "honesty": "Reads in-distribution DejaVu CAPTCHAs; 98/95 is NOT met. "
                   "A smoke selftest is not a benchmark.",
        "files_sha256": hashes,
    }
    (directory / "MANIFEST.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")

    archive = output / (name + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(output)).replace("\\", "/")
            item = zipfile.ZipInfo(rel, (2020, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = (0o100755 if p.name in ("start.sh", "start.command")
                                  else 0o100644) << 16
            z.writestr(item, p.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / (name + ".sha256.txt")).write_text(digest + "  " + archive.name + "\n")
    return {"directory": str(directory), "zip": str(archive), "sha256": digest,
            "bytes": archive.stat().st_size, "revision": revision, "dirty": dirty,
            "files": len(hashes), "fonts": len(FONT_NAMES)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, type=Path,
                   help="output DIRECTORY (created; receives <name>/ and <name>.zip)")
    p.add_argument("--allow-dirty", action="store_true")
    args = p.parse_args()
    try:
        print(json.dumps(build(args.out, args.allow_dirty), indent=2))
    except RuntimeError as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
