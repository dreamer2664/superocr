#!/usr/bin/env python3
"""Tests for the S3 structural repairs (t-20261011-407f).

Owns: split realignment, stitch seam detection + strip rolls, strippy
loose-cut row recovery, cut closing. The bar stays with the bench/S5; this
file pins the strategies with regression floors far below it.
Run:  python3 tests/test_reader_407f.py
"""
import sys
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


@check("split: undo_split realigns the halves (one text band again)")
def _split():
    for i in range(5):
        img, label = G.generate_one("split", seed=31, index=i)
        m = R.trim(R.otsu(R._lum(img)))
        u = R.trim(R.undo_split(m))
        cols = u.sum(axis=0)
        rows = np.where(cols > 0)[0]
        # after realignment the ink rows form one tight band, not two
        band = u.sum(axis=1)
        top = np.argmax(band > 0)
        bot = len(band) - np.argmax(band[::-1] > 0)
        assert (bot - top) <= 70, f"still two bands: {bot - top} rows"
        assert abs(len(R.segment(u)) - len(label.split())) <= 1


@check("stitch: seams detected, strips rolled back into one band")
def _stitch():
    for i in range(5):
        img, label = G.generate_one("stitch", seed=32, index=i)
        m = R.trim(R.otsu(R._lum(img)))
        u = R.trim(R.undo_stitch(img, m))
        band = u.sum(axis=1)
        top = np.argmax(band > 0)
        bot = len(band) - np.argmax(band[::-1] > 0)
        assert (bot - top) <= 80, f"strips not aligned: {bot - top} rows"


@check("strippy: loose cut recovers stripe-hidden rows")
def _strippy():
    for i in range(5):
        img, label = G.generate_one("strippy", seed=33, index=i)
        a = R._lum(img)
        tight = R.otsu(a)
        loose = R.otsu(a) | (a <= 220)
        assert loose.sum() > 1.3 * tight.sum(), "loose cut recovered nothing"
        assert loose.mean() < 0.15, "loose cut swallowed the background"


@check("cut: closing bridges the slashes without merging words")
def _cut():
    for i in range(5):
        img, label = G.generate_one("cut", seed=34, index=i)
        m = R.trim(R.otsu(R._lum(img)))
        c = R.trim(R.vclose(m, 4))
        assert c.sum() >= m.sum()
        assert abs(len(R.segment(c)) - len(label.split())) <= 2


@check("honest measurement: floors held, failures published")
def _score():
    floors = {"split": 0.40, "stitch": 0.30, "strippy": 0.15, "cut": 0.15}
    for fam, floor in floors.items():
        r = R.score(fam, 20, 7)
        assert r["char_acc"] >= floor, (
            f"{fam} char_acc {r['char_acc']:.2f} below floor {floor}")


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
    print(f"OK: all {len(CHECKS)} structural checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
