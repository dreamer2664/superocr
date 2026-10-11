#!/usr/bin/env python3
"""Tests for the typer (t-20261011-7b9f). Run: python3 tests/test_typer.py"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TYPER = ROOT / "typer.py"
CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def r2_text(p):
    r = subprocess.run([sys.executable, str(TYPER), str(p)],
                       capture_output=True, text=True, timeout=600)
    return r.stdout.strip()


def run(args, **kw):
    env = dict(os.environ)
    env.update(kw.pop("env", {}))
    return subprocess.run([sys.executable, str(TYPER), *args],
                          capture_output=True, text=True, env=env, timeout=600)


@check("file target: recognised text appended, family reported")
def _file():
    img, label = G.generate_one("easy", seed=50, index=0)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "in.png"
        out = Path(td) / "field.txt"
        img.save(p)
        r = run([str(p), "--target", f"file:{out}"])
        assert r.returncode == 0, r.stderr
        # the typer's contract is wiring, not OCR quality (the bench owns
        # accuracy): what recognise() says is what lands in the field
        assert out.read_text().strip() == r2_text(p)
        assert "target=file" in r.stderr


@check("crop: region geometry honoured")
def _crop():
    img, label = G.generate_one("easy", seed=51, index=0)
    canvas = __import__("PIL.Image", fromlist=["x"]).new("RGB", (img.width + 80, img.height + 60), (250, 250, 250))
    canvas.paste(img, (40, 30))
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "big.png"
        out = Path(td) / "field.txt"
        canvas.save(p)
        r = run([str(p), "--crop", f"{img.width}x{img.height}+40+30",
                 "--target", f"file:{out}"])
        assert r.returncode == 0, r.stderr
        # same pixels, same text: cropped region == the plain image alone
        assert out.read_text().strip() == r2_text_plain(str(p), img)


def r2_text_plain(path, img):
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td2:
        q = Path(td2) / "plain.png"
        img.save(q)
        r = subprocess.run([sys.executable, str(TYPER), str(q)],
                           capture_output=True, text=True, timeout=600)
        return r.stdout.strip()


@check("stdout default is safe; unknown target rejected")
def _stdout():
    img, label = G.generate_one("easy", seed=52, index=0)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "in.png"
        img.save(p)
        r = run([str(p)])
        assert r.returncode == 0 and len(r.stdout.strip()) > 0
        r = run([str(p), "--target", "telepathy"])
        assert r.returncode != 0 and "unknown target" in r.stderr


@check("missing desktop tool: honest error, no silent failure")
def _noxdo():
    img, _ = G.generate_one("easy", seed=53, index=0)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "in.png"
        img.save(p)
        r = run([str(p), "--target", "xdo"], env={"PATH": "/nonexistent"})
        assert r.returncode != 0
        assert "stdout" in (r.stderr + r.stdout), "no fallback guidance"


def main():
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
    if failed:
        print(f"{failed} check(s) failed")
        return 1
    print(f"OK: all {len(CHECKS)} typer checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
