#!/usr/bin/env python3
"""Tests for the S3 reader (t-20261011-2ca7): obstruction + dark-on-dark.

These tests check the STRATEGIES and the measurement harness, not the bar.
The bar (95/100 hard) is measured by the bench (t-2f3d) over the full reader
chain and proven by S5 (t-b0cb); this file pins what t-2ca7 owns:

  * dark-on-dark inversion/high-pass recovers the ink from the vignette;
  * obstruction high-pass removes the smudge while keeping the ink;
  * segmentation yields the right word count on clean cases;
  * the reader is deterministic and its CLI reads a file;
  * honest measurement: the score harness runs, publishes exact+char acc and
    a failure list; a regression floor (well below the bar) catches breakage
    without pretending the war is won.
Run:  python3 tests/test_reader_2ca7.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402
import reader as R  # noqa: E402

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("dark-on-dark: high-pass finds the ink, vignette gone")
def _dod_mask():
    for i in range(6):
        img, label = G.generate_one("dark-on-dark", seed=20, index=i)
        resid = R.preprocess(img, "dark-on-dark")
        m = R.binarize(resid, "dark-on-dark")
        assert 0.004 < m.mean() < 0.25, f"ink fraction {m.mean():.3f}"
        # ink lives in the middle band, not at the vignetted corners
        H, W = m.shape
        assert m[:, :W // 8].mean() < 0.02, "vignette leaked into the mask"


@check("obstruction: smudge removed, ink kept")
def _obs_mask():
    for i in range(6):
        img, label = G.generate_one("obstruction", seed=21, index=i)
        resid = R.preprocess(img, "obstruction")
        m = R.binarize(resid, "obstruction")
        assert 0.01 < m.mean() < 0.25, f"ink fraction {m.mean():.3f}"
        words = R.segment(m)
        n_expect = len(label.split())
        assert abs(len(words) - n_expect) <= 1, \
            f"words {len(words)} vs {n_expect} for {label!r}"


@check("reader deterministic and CLI-readable")
def _det_cli():
    img, label = G.generate_one("obstruction", seed=5, index=0)
    t1, _ = R.read(img, "obstruction")
    t2, _ = R.read(img, "obstruction")
    assert t1 == t2
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.png"
        img.save(p)
        r = subprocess.run([sys.executable,
                            str(Path(__file__).resolve().parent.parent / "reader.py"),
                            str(p), "--family", "obstruction"],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0 and r.stdout.strip() == t1


@check("honest measurement: score() reports acc + failures; floor held")
def _score_harness():
    for fam, floor in (("obstruction", 0.30), ("dark-on-dark", 0.35)):
        r = R.score(fam, 20, 7)
        assert r["n"] == 20 and 0.0 <= r["exact_acc"] <= 1.0
        assert r["char_acc"] >= floor, (
            f"{fam} char_acc {r['char_acc']:.2f} below regression floor {floor} "
            "(the strategy regressed; look at reports/ for the last truth)")
        assert isinstance(r["failures"], list)
        for i, lab, got in r["failures"]:
            assert lab != got


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
    print(f"OK: all {len(CHECKS)} reader checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
