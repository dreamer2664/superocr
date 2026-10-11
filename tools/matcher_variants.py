#!/usr/bin/env python3
"""tools/matcher_variants.py — corrosion matcher experiment (t-20261011-be57).

Diagnosis says corrosion is a pure classifier failure (seg 1.02/true,
100% of seg-OK images misread). reader._score_glyph tolerates 1px pits;
generator chews bigger holes into heavy strokes. This tool re-reads the
identical segmentation through matcher VARIANTS and reports which one
lifts corrosion without touching the controls (easy, snow).

Variants (numpy-only, all deterministic):
  raw        the shipped scorer (control)
  close1/2   glyph mask morphologically closed (dilate+erode) k times
  dilate1/2  glyph dilated k px (hole-bridging, no erosion step)
  union      max(raw, score of close2) — "dual-pass"
  cover      asymmetric: template-ink coverage by dilate2(glyph),
             gated by glyph-ink precision to stop blob matches

    python3 tools/matcher_variants.py --out reports/matcher-variants.json
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402
import generator as G  # noqa: E402
import reader as R  # noqa: E402

SAME_SHAPE = "CcOoSsVvWwZzKkPpUuXx"


def _dilate(m: np.ndarray) -> np.ndarray:
    d = m.copy()
    d[1:, :] |= m[:-1, :]
    d[:-1, :] |= m[1:, :]
    d[:, 1:] |= m[:, :-1]
    d[:, :-1] |= m[:, 1:]
    return d


def _erode(m: np.ndarray) -> np.ndarray:
    e = m.copy()
    e[1:, :] &= m[:-1, :]
    e[:-1, :] &= m[1:, :]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    return e


def _close(m: np.ndarray, k: int) -> np.ndarray:
    for _ in range(k):
        m = _dilate(m)
    for _ in range(k):
        m = _erode(m)
    return m


def _cover_score(g: np.ndarray, t: np.ndarray) -> float:
    H, W = max(g.shape[0], t.shape[0]), max(g.shape[1], t.shape[1])
    gp = np.zeros((H, W), bool); gp[:g.shape[0], :g.shape[1]] = g
    tp = np.zeros((H, W), bool); tp[:t.shape[0], :t.shape[1]] = t
    gd = _dilate(_dilate(gp))
    cover = float((tp & gd).sum()) / float(tp.sum() or 1)
    prec = float((gp & tp).sum()) / float(gp.sum() or 1)
    return cover * prec


def score_variant(name: str, g: np.ndarray, t: np.ndarray) -> float:
    if name == "raw":
        return R._score_glyph(g, t)
    if name == "close1":
        return R._score_glyph(_close(g, 1), t)
    if name == "close2":
        return R._score_glyph(_close(g, 2), t)
    if name == "dilate1":
        return R._score_glyph(_dilate(g), t)
    if name == "dilate2":
        return R._score_glyph(_dilate(_dilate(g)), t)
    if name == "union":
        return max(R._score_glyph(g, t), R._score_glyph(_close(g, 2), t))
    if name == "cover":
        return _cover_score(g, t)
    raise ValueError(name)


VARIANTS = ["raw", "close1", "close2", "dilate1", "dilate2", "union", "cover"]


@functools.lru_cache(maxsize=64)
def _cands_window(h: int, window: int) -> tuple[tuple[str, object, np.ndarray], ...]:
    """_cands_for_height with a caller-set height tolerance (±window px)."""
    cands = []
    for nominal in range(max(10, h - window), min(72, 2 * h + 4 + window)):
        for (ch, face), t in B._templates_native(nominal).items():
            if abs(t.shape[0] - h) <= window:
                cands.append((ch, face, t))
    return tuple(cands)


def match_with(variant: str, mask: np.ndarray, window: int = 1) -> tuple[str, float]:
    """variant scorers; `window` is the candidate height tolerance
    (±1 shipped in _cands_for_height)."""
    best = ("?", -1.0)
    for ch, face, t in _cands_window(mask.shape[0], window):
        s = score_variant(variant, mask, t)
        if s > best[1]:
            best = (ch, s)
    return best


def read_with(variant: str, img: Image.Image, window: int = 0) -> str:
    """The floor chain verbatim, with match_native swapped for a variant."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.trim(R.despeck(R.otsu(a)))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    words = R.segment(mask)
    out = []
    for word in words:
        pieces = []
        for x0, x1 in word:
            for g in R.split_wide(R.trim(mask[:, x0:x1])):
                if g.shape[0] >= 6 and g.sum() >= 10:
                    pieces.append(g)
        if not pieces:
            continue
        cap = max(g.shape[0] for g in pieces)
        chars = []
        for g in pieces:
            ch, s = match_with(variant, g, window)
            if ch in SAME_SHAPE:
                ch = ch.lower() if g.shape[0] < 0.85 * cap else ch.upper()
            chars.append(ch)
        if chars:
            out.append("".join(chars))
    return " ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--families", default="corrosion,easy,snow")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--out", help="json report path")
    args = ap.parse_args()

    fams = [f for f in args.families.split(",") if f]
    variants = [v for v in args.variants.split(",") if v]
    # name or name:window (height tolerance ±window)
    t0 = time.time()
    cache = {}
    for fam in fams:
        cache[fam] = [G.generate_one(fam, seed=args.seed, index=i)
                      for i in range(args.count)]
    rows = []
    for fam in fams:
        for var in variants:
            name, _, w = var.partition(":")
            window = int(w) if w else 1
            exact = 0
            td = []
            for img, label in cache[fam]:
                st = time.time()
                text = read_with(name, img, window)
                td.append(time.time() - st)
                exact += text == label
            score_variant(name, np.zeros((8, 8), bool), np.zeros((8, 8), bool))  # validate early
            rows.append({"family": fam, "variant": var,
                         "exact": round(exact / args.count, 2),
                         "median_s": round(sorted(td)[len(td) // 2], 3)})
    report = {"seed": args.seed, "count": args.count, "rows": rows,
              "seconds": round(time.time() - t0, 1)}
    print(f"matcher variants — {args.count}/family, seed {args.seed}, {report['seconds']}s")
    cur = None
    for r in rows:
        if r["family"] != cur:
            cur = r["family"]
            print(f"  {cur}:")
        print(f"    {r['variant']:<8} exact {r['exact']*100:5.0f}%  median {r['median_s']}s")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")


if __name__ == "__main__":
    main()
