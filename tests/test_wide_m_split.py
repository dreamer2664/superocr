#!/usr/bin/env python3
"""Regression lock for t-20261011-31af (pericles' slot, five hands): split_wide must never
halve a wide glyph again, and must never stop splitting genuine touching glyphs.

    python3 tests/test_wide_m_split.py

Two seeded cases, opposite failure modes:
  wide-M  (M stretched x2.0, ratio 1.43) -> exactly 1 piece (the bug: it used to give 2)
  il-pair (i touching l, x1.15, ratio 1.51) -> 2 pieces (an over-eager fix must not merge)
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw  # noqa: E402

import generator as G  # noqa: E402
import reader  # noqa: E402

failures = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  {extra}"))
    if not cond:
        failures.append(name)


def mask_of(text: str, stretch: float, seed: int = 7, size: int = 48):
    font = G.load_font(random.Random(seed), size)
    img = Image.new("L", (400, 120), 255)
    ImageDraw.Draw(img).text((10, 10), text, font=font, fill=0)
    if stretch != 1.0:
        img = img.resize((int(400 * stretch), 120), Image.LANCZOS)
    return reader.trim(reader.otsu(reader._lum(img)))


def main() -> int:
    wide_m = mask_of("M", stretch=2.0)
    pieces = reader.split_wide(wide_m)
    h, w = wide_m.shape
    check("a wide M is ONE glyph, not two narrow letters", len(pieces) == 1,
          f"got {len(pieces)} pieces at ratio {w/h:.2f} (the t-31af bug)")

    il_pair = mask_of("il", stretch=1.15)
    pieces = reader.split_wide(il_pair)
    h, w = il_pair.shape
    check("a genuine touching i+l pair still splits into two", len(pieces) == 2,
          f"got {len(pieces)} pieces at ratio {w/h:.2f} (over-merge regression)")

    if failures:
        print()
        print(f"failing: {', '.join(failures)}")
        return 1
    print("OK: wide glyphs stay whole, real boundaries still split")
    return 0


if __name__ == "__main__":
    sys.exit(main())
