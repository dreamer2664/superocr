#!/usr/bin/env python3
"""tools/s8_resplit.py — S8 lever C experiment: rescue-re-split (t-20261012-ac4f).

Taxonomy on the official easy suite (seed 1): 20 under-split images with
touching pairs fused ('rb'->I, 'al'->b, 'rf'->H). split_wide only fires
above 1.35 w/h and only searches the middle 60% of columns, so a fused
pair at borderline width survives. Lever C is a matcher-side re-read:

for every piece whose match confidence is low (< --conf-gate) AND whose
width allows two glyphs (w/h > --wh-gate), try every column cut in the
middle band and accept the split when BOTH halves template-match and the
worse half beats the unsplit piece by --margin. Floor-local, no change to
reader.py (marcus's split_wide front).

    python3 tools/s8_resplit.py --family easy --count 40 --seed 7
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402
import generator as G  # noqa: E402
import reader as R  # noqa: E402


def _char_acc(label: str, text: str) -> float:
    l1, l2 = label.replace(" ", ""), text.replace(" ", "")
    tot = max(len(l1), len(l2)) or 1
    return sum(a == b for a, b in zip(l1, l2)) / tot


def rescue_split(piece: np.ndarray, conf_gate: float, wh_gate: float,
                 margin: float) -> list[np.ndarray]:
    ch0, s0 = B.match_native(piece)
    if s0 >= conf_gate and piece.shape[1] <= wh_gate * piece.shape[0]:
        return [piece]
    h, w = piece.shape
    best = None
    colsum = piece.sum(axis=0)
    for x in range(max(2, int(w * 0.12)), max(3, int(w * 0.88))):
        left, right = R.trim(piece[:, :x]), R.trim(piece[:, x:])
        if not left.any() or not right.any():
            continue
        if left.shape[0] < 6 or right.shape[0] < 6 or left.sum() < 10 or right.sum() < 10:
            continue
        _, s_l = B.match_native(left)
        _, s_r = B.match_native(right)
        score = min(s_l, s_r)
        if best is None or score > best[0]:
            best = (score, x, left, right, s_l, s_r)
    if best and best[0] >= s0 + margin:
        _, x, left, right, s_l, s_r = best
        return [left, right]
    return [piece]


def read_resplit(img: Image.Image, conf_gate: float, wh_gate: float,
                 margin: float, enabled: bool = True) -> str:
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.otsu(a)
    if mask.mean() > 0.5:
        mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    out = []
    for word in R.segment(mask):
        pieces = []
        for x0, x1 in word:
            for g in B._merge_forced(B._split_marked(R.trim(mask[:, x0:x1]))):
                if g.shape[0] >= 6 and g.sum() >= 10:
                    pieces.append(g)
        if not pieces:
            continue
        if enabled:
            rescued = []
            for g in pieces:
                rescued.extend(rescue_split(g, conf_gate, wh_gate, margin))
            pieces = rescued
        cap = max(g.shape[0] for g in pieces)
        chars = []
        for g in pieces:
            ch, _ = B.match_native(g)
            if ch in B.SAME_SHAPE:
                ch = ch.lower() if g.shape[0] < 0.85 * cap else ch.upper()
            chars.append(ch)
        if chars:
            out.append("".join(chars))
    return " ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="easy")
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--conf-gate", type=float, default=0.72)
    ap.add_argument("--wh-gate", type=float, default=0.85)
    ap.add_argument("--margin", type=float, default=0.05)
    args = ap.parse_args()

    fams = [f for f in args.family.split(",") if f]
    for fam in fams:
        rows = {}
        for name, enabled in (("base", False), ("resplit", True)):
            ex, cok = 0, 0.0
            for i in range(args.count):
                img, label = G.generate_one(fam, seed=args.seed, index=i)
                text = read_resplit(img, args.conf_gate, args.wh_gate,
                                    args.margin, enabled)
                ex += text == label
                cok += _char_acc(label, text)
            rows[name] = (ex, cok)
        b_e, b_c = rows["base"]
        r_e, r_c = rows["resplit"]
        print(f"{fam:<13} seed {args.seed} N={args.count}: base {b_e}/{args.count} "
              f"({b_c/args.count:.3f}c) -> resplit {r_e}/{args.count} ({r_c/args.count:.3f}c) "
              f"[gate {args.conf_gate}, w/h {args.wh_gate}, margin {args.margin}]")


if __name__ == "__main__":
    main()
