#!/usr/bin/env python3
"""tools/s15_margins.py — S15 receipt: template-margin + topology survey of
the hard floor's glyphs (t-20261012-cf09).

Rebuilds the baseline floor pipeline stage by stage on every non-wall hard
suite item, aligns the read against the label (Levenshtein backtrace), and
records for every emitted glyph: the top1-top2 template margin, the mask
hole count, and whether the glyph was right. What it showed (official
suite, seed 1, hash b2c460d2fb5a, main a7168d5b): 100% of hard-floor
matches sit inside a 0.05 template margin — right or wrong — so no cheap
decision lever has signal to work with; see reports/s15-xheight-smalls.md.

    python3 tools/s15_margins.py --suite-dir /tmp/review-suites \
        --bench-json reports/<stem>-easy-hard.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import baseline as B  # noqa: E402
import reader as R  # noqa: E402

WALLS = {"spiderweb", "collage", "cross-shadow", "darts", "split", "stitch"}


def _pieces_of(img: Image.Image) -> list[np.ndarray]:
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.otsu(a)
    if mask.mean() > 0.5:
        mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    pieces = []
    for word in R.segment(mask):
        for x0, x1 in word:
            for g0 in B._merge_forced(B._split_marked(R.trim(mask[:, x0:x1]))):
                if g0.shape[0] >= 6 and g0.sum() >= 10:
                    pieces.append(g0)
    return pieces


def _align(a: str, b: str) -> list[tuple[int, str, str]]:
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    i, j, out = la, lb, []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            out.append((i - 1, a[i - 1], b[j - 1])); i -= 1; j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            out.append((i - 1, a[i - 1], "x")); i -= 1
        else:
            j -= 1
    return out[::-1]


def _holes(piece: np.ndarray) -> int:
    p = np.pad(~piece, 1)
    seen = np.zeros_like(p, bool)
    n, H, W = -1, p.shape[0], p.shape[1]
    for i in range(H):
        for j in range(W):
            if p[i, j] and not seen[i, j]:
                n += 1
                stack = [(i, j)]
                seen[i, j] = True
                while stack:
                    y, x = stack.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx < W and p[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
    return n


def _top2(g: np.ndarray) -> list[tuple[float, str]]:
    scored = sorted(((R._score_glyph(g, t), ch)
                     for ch, face, t in B._cands_for_height(g.shape[0])), reverse=True)
    return scored[:2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--suite-dir", required=True)
    ap.add_argument("--bench-json", required=True,
                    help="bench report JSON with per-image results")
    args = ap.parse_args(argv)
    rep = json.load(open(args.bench_json))
    m_err, m_ok, holes_err = [], [], []
    for r in rep["suites"]["hard"]["results"]:
        if r["match"] or r["family"] in WALLS:
            continue
        img = Image.open(Path(args.suite_dir) / "hard" / "images" / f"{r['id']}.png")
        text, _ = B.read_text(img, None)
        got = text.replace(" ", "")
        pieces = _pieces_of(img)
        if len(pieces) != len(got):
            continue
        for idx, ec, gc in _align(r["label"].replace(" ", ""), got):
            if gc == "x" or idx >= len(pieces):
                continue
            t = _top2(pieces[idx])
            if len(t) < 2:
                continue
            m = t[0][0] - t[1][0]
            if ec != gc:
                m_err.append(m)
                holes_err.append(_holes(pieces[idx]))
            else:
                m_ok.append(m)
    me, mo = np.array(m_err), np.array(m_ok)
    print(f"wrong glyphs: {len(me)} | correct glyphs: {len(mo)}")
    print(f"margin medians: wrong {np.median(me):.3f} | correct {np.median(mo):.3f}")
    for thr in (0.01, 0.02, 0.05, 0.10):
        print(f"  margin<{thr}: wrong {(me < thr).sum()}/{len(me)} "
              f"({(me < thr).mean():.0%}) | correct {(mo < thr).sum()}/{len(mo)} "
              f"({(mo < thr).mean():.0%})")
    print(f"hole counts on wrong glyphs: min {min(holes_err)} max {max(holes_err)}"
          f" (no class signature — masks fragmented under distortion)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
