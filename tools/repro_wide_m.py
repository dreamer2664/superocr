#!/usr/bin/env python3
"""t-20261011-31af repro slot (pericles): wide-M must survive split_wide; a genuine il-pair must still split.

Run: python3 tools/repro_wide_m.py
Pre-fix expectation : wide-M 2 pieces (BUG), il-pair 2 (correct).
Post-fix expectation: wide-M 1 piece, il-pair 2 (the fix must not over-merge).
Owner of the fix: marcus-aurelius (cut-metadata hoist into shared split_wide).
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw  # noqa: E402

import generator as G  # noqa: E402
import reader  # noqa: E402


def mask_of(text: str, stretch: float, seed: int = 7, size: int = 48):
    font = G.load_font(random.Random(seed), size)
    img = Image.new("L", (400, 120), 255)
    ImageDraw.Draw(img).text((10, 10), text, font=font, fill=0)
    if stretch != 1.0:
        img = img.resize((int(400 * stretch), 120), Image.LANCZOS)
    return reader.trim(reader.otsu(reader._lum(img)))


wide_m = mask_of("M", stretch=2.0)
il_pair = mask_of("il", stretch=1.15)
m_pieces, il_pieces = len(reader.split_wide(wide_m)), len(reader.split_wide(il_pair))
h, w = wide_m.shape
print(f"wide-M   (seed 7, size 48, x2.0): w={w} h={h} ratio={w/h:.2f} -> {m_pieces} piece(s)  [want 1; 2 = bug]")
h, w = il_pair.shape
print(f"il-pair  (seed 7, size 48, x1.15): w={w} h={h} ratio={w/h:.2f} -> {il_pieces} piece(s)  [want 2; must stay split]")
print("VERDICT:", "BUG PRESENT (wide-M over-split)" if m_pieces != 1 else "wide-M intact", "|",
      "il-pair OK" if il_pieces >= 2 else "il-pair OVER-MERGED")
