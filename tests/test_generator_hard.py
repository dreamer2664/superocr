#!/usr/bin/env python3
"""Tests for the hard-family generator (t-20261011-e071).

What the bench (and Carlo's bar) depend on:
  1. every family produces a real RGB image + a non-empty printable label;
  2. same seed -> byte-identical PNG (reproducibility is the whole point);
  3. labels are exact ground truth: printable ASCII, several words, mixed
     case, digits in some fraction of labels;
  4. the dataset writer's manifest matches the files on disk, and re-running
     with the same seed reproduces every byte.
Run:  python3 tests/test_generator_hard.py
"""
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def png_bytes(img) -> bytes:
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


@check("all twelve families produce image + label")
def _families():
    assert set(G.FAMILIES) == {
        "snow", "spiderweb", "split", "stitch", "strippy", "cut", "collage",
        "corrosion", "cross-shadow", "darts", "obstruction", "dark-on-dark",
    }, f"family set changed: {sorted(G.FAMILIES)}"
    for fam in G.FAMILIES:
        img, label = G.generate_one(fam, seed=1234)
        assert img.mode == "RGB" and img.size == G.DEFAULT_SIZE, fam
        assert isinstance(label, str) and label.strip(), fam
        assert all(32 <= ord(c) < 127 for c in label), f"{fam}: non-printable in {label!r}"
        # the image actually contains ink (not a blank canvas). Global std is
        # the wrong probe: dark-on-dark is adversarial BY DESIGN (a few steps
        # of contrast), so count distinct luminance levels instead -- grain
        # alone gives a handful, ink+vignette must add more.
        import numpy as np
        lum = np.array(img.convert("L"))
        assert len(np.unique(lum)) > 12, f"{fam}: suspiciously flat image"


@check("determinism: same seed twice -> byte-identical PNGs")
def _determinism():
    for fam in G.FAMILIES:
        i1, l1 = G.generate_one(fam, seed=777)
        i2, l2 = G.generate_one(fam, seed=777)
        assert l1 == l2, fam
        assert png_bytes(i1) == png_bytes(i2), f"{fam}: PNG bytes differ for same seed"
    # different seeds -> different labels in at least most families
    diff = sum(G.generate_one(f, 1)[1] != G.generate_one(f, 2)[1] for f in G.FAMILIES)
    assert diff >= 10, f"seeds barely matter: only {diff}/12 families change"


@check("labels: several words, mixed case, digits appear")
def _labels():
    n_words_total, with_digits, with_upper, with_lower = 0, 0, 0, 0
    for fam in G.FAMILIES:
        for i in range(12):
            _, label = G.generate_one(fam, seed=5, index=i)
            toks = label.split(" ")
            assert len(toks) >= 2, f"{fam}[{i}]: single word {label!r}"
            n_words_total += len(toks)
            with_digits += bool(re.search(r"\d", label))
            with_upper += bool(re.search(r"[A-Z]", label))
            with_lower += bool(re.search(r"[a-z]", label))
    n = 12 * len(G.FAMILIES)
    assert with_digits / n > 0.25, f"too few digit labels: {with_digits}/{n}"
    assert with_upper / n > 0.5, f"too few uppercase labels: {with_upper}/{n}"
    assert with_lower / n > 0.9, f"too few lowercase labels: {with_lower}/{n}"
    assert n_words_total / n >= 2.5, f"labels too short: {n_words_total / n:.2f} words avg"


@check("dataset writer: manifest matches files, re-run reproduces every byte")
def _dataset(tmp=Path(tempfile.mkdtemp(prefix="gen_"))):
    out1, out2 = tmp / "a", tmp / "b"
    r1 = G.write_dataset("snow", 3, seed=99, outdir=out1, size=(320, 100))
    r2 = G.write_dataset("snow", 3, seed=99, outdir=out2, size=(320, 100))
    assert r1 == r2
    man = [json.loads(l) for l in (out1 / "manifest.jsonl").read_text().splitlines()]
    assert len(man) == 3
    for row in man:
        f = out1 / row["file"]
        assert f.exists(), row["file"]
        assert (out1 / row["file"]).read_bytes() == (out2 / row["file"]).read_bytes()
        assert row["label"].strip() and row["family"] == "snow"
    # 'all' covers every family exactly once per index
    out3 = tmp / "all"
    rows = G.write_dataset("all", 1, seed=3, outdir=out3, size=(240, 90))
    assert {r["family"] for r in rows} == set(G.FAMILIES)


@check("CLI: --list, unknown family rejected, --out writes pngs + manifest")
def _cli():
    here = Path(__file__).resolve().parent.parent / "generator.py"
    r = subprocess.run([sys.executable, str(here), "--list"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "snow" in r.stdout and "dark-on-dark" in r.stdout
    r = subprocess.run([sys.executable, str(here), "--family", "bogus"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and "unknown family" in r.stderr
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, str(here), "--family", "cut",
                            "--count", "2", "--seed", "7", "--out", td],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr
        files = sorted(Path(td).glob("*.png"))
        assert len(files) == 2 and (Path(td) / "manifest.jsonl").exists()


@check("no font required: graceful fallback when DejaVu is absent")
def _font_fallback():
    saved, G._FONT_CANDIDATES = G._FONT_CANDIDATES, ["/nonexistent/x.ttf"]
    try:
        img, label = G.generate_one("cut", seed=9)
        assert img.size == G.DEFAULT_SIZE and label.strip()
    finally:
        G._FONT_CANDIDATES = saved


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
    print(f"OK: all {len(CHECKS)} generator checks passed "
          f"({len(G.FAMILIES)} families: {', '.join(G.FAMILIES)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
