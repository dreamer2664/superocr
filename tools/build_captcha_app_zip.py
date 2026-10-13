#!/usr/bin/env python3
"""build_captcha_app_zip.py — deterministic zip of apps/captcha-studio/.

Deterministic = same bytes for the same input tree, on any machine:
entries sorted by name, mtime pinned to the zip epoch (1980-01-01),
no extra fields, deflate level 9. The zip root is a single
`captcha-studio/` directory, so users can unzip anywhere.

Usage:
    python3 tools/build_captcha_app_zip.py --out captcha-studio.zip
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = REPO / "apps" / "captcha-studio"
ZIP_ROOT = "captcha-studio"
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

SKIP_SUFFIXES = (".pyc", ".pyo", ".DS_Store")
SKIP_DIRS = ("__pycache__", ".git", ".mypy_cache")


def iter_payload(src: Path):
    for p in sorted(src.rglob("*")):
        if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix in SKIP_SUFFIXES:
            continue
        yield p, f"{ZIP_ROOT}/{p.relative_to(src).as_posix()}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC,
                    help="app directory (default: apps/captcha-studio)")
    ap.add_argument("--out", type=Path, required=True, help="output zip path")
    args = ap.parse_args()

    src = args.src.resolve()
    if not (src / "run.py").exists():
        raise SystemExit(f"{src} does not look like the app dir (no run.py)")

    entries = list(iter_payload(src))
    if not entries:
        raise SystemExit(f"{src} is empty")
    for _, arc in entries:
        if arc != arc.encode("utf-8", "strict").decode("utf-8"):
            raise SystemExit(f"non-utf8 path: {arc}")

    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(out, "w", ZIP_DEFLATED, compresslevel=9) as zf:
        for p, arc in entries:
            info = ZipInfo(arc, date_time=ZIP_EPOCH)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3              # Unix: record sane rwx bits
            info.external_attr = (0o644 if p.stat().st_mode & 0o111 == 0
                                  else 0o755) << 16
            zf.writestr(info, p.read_bytes())

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(entries)} files)")
    print(f"sha256 {digest}")
    print("unzip -> cd captcha-studio -> python3 run.py  (browser opens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
