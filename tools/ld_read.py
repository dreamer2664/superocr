#!/usr/bin/env python3
"""tools/ld_read.py — EXPERIMENTAL local-diff chain (t-20261011-be57 p2).

NOT wired into baseline.py or reader.py on purpose: the merge-back
arbiter regresses easy exact (see reports/cross-shadow-root-cause.md).
Kept so every number in that report reproduces:

    python3 tools/ld_read.py --family cross-shadow --count 10 --seed 7
    python3 tools/ld_read.py --family snow --no-ld --merge

  --no-ld    use the classic autocontrast+otsu mask (polarity-guarded)
             instead of the local-diff binarisation
  --merge    enable the greedy merge-back arbiter (max-conf rule,
             dot/stem height-mismatch guard)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402
from baseline import SAME_SHAPE  # noqa: E402  # never re-literal this set
import generator as G  # noqa: E402
import reader as R  # noqa: E402

LOCAL_TH = 60
LOCAL_R = 25


def boxmean(a: np.ndarray, r: int) -> np.ndarray:
    """Mean of the (2r+1)^2 neighbourhood via integral image, O(1)/pixel."""
    I = np.pad(a, ((r + 1, r), (r + 1, r))).cumsum(0).cumsum(1)
    h, w = a.shape
    return (I[2*r+1:2*r+1+h, 2*r+1:2*r+1+w] - I[:h, 2*r+1:2*r+1+w]
            - I[2*r+1:2*r+1+h, :w] + I[:h, :w]) / ((2 * r + 1) ** 2)


def merge_back(pieces: list[np.ndarray]) -> list[np.ndarray]:
    """Greedily merge adjacent pieces when the merged glyph matches at
    least as confidently as the more confident part. Never merges across
    the 1.6x height mismatch that marks dot-over-stem pairs."""
    changed = True
    while changed and len(pieces) > 1:
        changed = False
        best = None
        for j in range(len(pieces) - 1):
            a, b = pieces[j], pieces[j + 1]
            if max(a.shape[0], b.shape[0]) / max(1, min(a.shape[0], b.shape[0])) > 1.6:
                continue
            H, W = max(a.shape[0], b.shape[0]), a.shape[1] + b.shape[1]
            m = np.zeros((H, W), bool)
            m[:a.shape[0], :a.shape[1]] |= a
            m[:b.shape[0], a.shape[1]:a.shape[1] + b.shape[1]] |= b
            m = R.trim(m)
            _, s_m = B.match_native(m)
            _, s_a = B.match_native(a)
            _, s_b = B.match_native(b)
            if s_m >= max(s_a, s_b):
                gain = s_m - max(s_a, s_b)
                if best is None or gain > best[0]:
                    best = (gain, j, m)
        if best:
            _, j, m = best
            pieces[j:j + 2] = [m]
            changed = True
    return pieces


def read(img, use_ld: bool, do_merge: bool) -> str:
    a = np.array(img.convert("L"), dtype=np.float32)
    if use_ld:
        mask = (boxmean(a, LOCAL_R) - a) > LOCAL_TH
    else:
        g = ImageOps.autocontrast(img.convert("L"), cutoff=0)
        mask = R.otsu(np.array(g, dtype=np.float32))
    if mask.mean() > 0.5:  # polarity guard, same as the shipped floor
        mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    out = []
    for word in R.segment(mask):
        pieces = []
        for x0, x1 in word:
            for g in R.split_wide(R.trim(mask[:, x0:x1])):
                if g.shape[0] >= 6 and g.sum() >= 10:
                    pieces.append(g)
        if not pieces:
            continue
        if do_merge:
            pieces = merge_back(pieces)
        cap = max(g.shape[0] for g in pieces)
        chars = []
        for g in pieces:
            ch, _ = B.match_native(g)
            if ch in SAME_SHAPE:
                ch = ch.lower() if g.shape[0] < 0.85 * cap else ch.upper()
            chars.append(ch)
        if chars:
            out.append("".join(chars))
    return " ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="cross-shadow")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-ld", action="store_true")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    fams = [f for f in args.family.split(",") if f]
    for fam in fams:
        ex, cok = 0, 0.0
        for i in range(args.count):
            img, label = G.generate_one(fam, seed=args.seed, index=i)
            text = read(img, not args.no_ld, args.merge)
            ex += text == label
            l1, l2 = label.replace(" ", ""), text.replace(" ", "")
            cok += sum(a == b for a, b in zip(l1, l2)) / max(len(l1), len(l2))
        tag = ("otsu" if args.no_ld else f"ld-th{LOCAL_TH}") + ("+merge" if args.merge else "")
        print(f"{fam:<14} {tag:<18} exact {ex}/{args.count}  char {cok/args.count:.3f}")


if __name__ == "__main__":
    main()
