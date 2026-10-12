#!/usr/bin/env python3
"""S20 corrosion — restoration probe (t-20261012-7c1b, marcus).

Measure-first: does ANY pre-classification restoration move the official
corrosion-8 off 0/8? The family chain already runs close_mask k=1 as its
primary (0.166 -> 0.186 char on seed-7 tens) and reads 0/8 exact on the
official suite (verified today, plain AND --family corrosion pinned).

Variants probe the pre-bin/gray domain so they compose with the chain:
  identity      — control
  med3 / med5   — grayscale median (hole fill that preserves edges)
  gclose2/3/4   — grayscale closing on inverted lum (heals pits <= 2k px)
  med3+gclose2  — composition

Runs baseline.read_text(img, family=None) on the RESTORED image, so every
number is end-to-end official-path text, not a mask similarity. Screens,
not proofs; one pass, N=8, exact + char accuracy both reported.

Usage: python3 tools/s20_restoration_probe.py [--suite-dir DIR]
"""
import argparse
import difflib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline  # noqa: E402


def char_acc(want: str, got: str) -> float:
    if not want:
        return 1.0 if not got else 0.0
    sm = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    return sm.ratio()


def gray_close(img: Image.Image, k: int) -> Image.Image:
    """Closing on inverted luminance: dilate dark ink over light pits,
    then erode back — fills holes up to 2k px in heavy strokes."""
    inv = Image.eval(img.convert("L"), lambda v: 255 - v)
    for _ in range(k):
        inv = inv.filter(ImageFilter.MaxFilter(3))
    for _ in range(k):
        inv = inv.filter(ImageFilter.MinFilter(3))
    return Image.eval(inv, lambda v: 255 - v).convert("L")


def fill_interior_holes(img: Image.Image, max_area: int) -> Image.Image:
    """Otsu-binarize, find background components NOT touching the border,
    fill the small enclosed ones with median ink luminance — the targeted
    repair for interior pits (as opposed to global closing, which also
    distorts thin strokes)."""
    from collections import deque

    import reader as R
    a = np.asarray(img.convert("L"), dtype=np.float32)
    mask = R.otsu(a)                                  # True = ink
    h, w = mask.shape
    bg = ~mask
    seen = np.zeros_like(bg, dtype=bool)
    out = img.convert("L").copy()
    ink_val = int(np.median(a[mask])) if mask.any() else 0

    def comp(i0, j0):
        q = deque([(i0, j0)])
        seen[i0, j0] = True
        cells = [(i0, j0)]
        while q:
            i, j = q.popleft()
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if 0 <= ni < h and 0 <= nj < w and bg[ni, nj] and not seen[ni, nj]:
                    seen[ni, nj] = True
                    q.append((ni, nj))
                    cells.append((ni, nj))
        touches = any(i in (0, h - 1) or j in (0, w - 1) for i, j in cells)
        return cells, touches

    for i in range(h):
        for j in range(w):
            if bg[i, j] and not seen[i, j]:
                cells, touches = comp(i, j)
                if not touches and len(cells) <= max_area:
                    for ci, cj in cells:
                        out.putpixel((cj, ci), ink_val)
    return out


def variants() -> list[tuple[str, callable]]:
    return [
        ("identity", lambda im: im),
        ("med3", lambda im: im.convert("L").filter(ImageFilter.MedianFilter(3))),
        ("med5", lambda im: im.convert("L").filter(ImageFilter.MedianFilter(5))),
        ("gclose2", lambda im: gray_close(im, 2)),
        ("gclose3", lambda im: gray_close(im, 3)),
        ("gclose4", lambda im: gray_close(im, 4)),
        ("med3+gclose2", lambda im: gray_close(
            im.convert("L").filter(ImageFilter.MedianFilter(3)), 2)),
        ("holefill4", lambda im: fill_interior_holes(im, 4)),
        ("holefill9", lambda im: fill_interior_holes(im, 9)),
        ("holefill16", lambda im: fill_interior_holes(im, 16)),
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite-dir", default="/tmp/review-suites",
                    help="official suite root (seed 1, hash b2c460d2fb5a)")
    args = ap.parse_args()

    man = [json.loads(l) for l in
           open(Path(args.suite_dir) / "hard" / "manifest.jsonl")]
    items = [r for r in man if r["family"] == "corrosion"]
    print(f"corrosion items: {len(items)}")
    print(f"{'variant':14s} exact  char   per-item")

    for name, fn in variants():
        exact = 0
        chars = []
        per = []
        for row in items:
            img = Image.open(Path(args.suite_dir) / "hard" / row["image"])
            try:
                restored = fn(img)
                text, _ = baseline.read_text(restored, None)
            except Exception as e:                              # noqa: BLE001
                text, _ = f"<{type(e).__name__}>", None
            got = (text or "").strip()
            want = row["label"]
            m = got == want
            exact += int(m)
            ca = char_acc(want, got)
            chars.append(ca)
            per.append(f"{row['id'][-4:]}:{'X' if m else str(round(ca, 2))[1:]}")
        line = f"{name:14s} {exact}/{len(items)}  {np.mean(chars):.3f}  " + " ".join(per)
        print(line)

    print()
    print("screens only (N=8, one pass) — compare to the identity control row;")
    print("no claim until a variant beats it across the table.")


if __name__ == "__main__":
    main()
