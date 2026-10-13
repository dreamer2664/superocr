#!/usr/bin/env python3
"""S27 (t-20261013-3cae): oracle masks on the six collapse families.

Question (from S25): the six families at ~0 (48/79 hard misses) fail at or
before the mask. How much of that wall is MASK-recoverable (ink survives the
degradation; only extraction fails) vs INK-DESTROYED / GEOMETRY-DOWNSTREAM
(even a perfect mask cannot read it through the unchanged pipeline)?

Oracle construction, per family (all replays use rng_for(family, seed, index)
so they are bit-faithful to the suite items):

  spiderweb, cross-shadow, strippy, darts
      the degradation only overlays/dims — ink pixels stay at their
      coordinates. Oracle = the clean render's ink, drawn as a binary
      document (ink black on white) and fed through baseline.read_text
      UNCHANGED (its own otsu on a binary image reproduces the mask exactly).

  corrosion
      pits ERASE ink. Oracle = the heavy-stroke render (same rng replay)
      minus the same pits (same rng_np stream, same positions/radii),
      as a binary document. The heavy stroke itself is part of the
      family's real difficulty and is kept.

  collage
      word cards built from scratch, each rotated ±9 deg. Oracle = the same
      words drawn as black-on-white cards, rotated and pasted at the same
      positions (full rng replay, color calls consumed to keep the stream
      aligned). This measures the downstream (single-angle deskew) ceiling.

Output: per-family table of misses -> oracle-exact / oracle-miss, written to
reports/s27-oracle-masks/ (rows.jsonl + table.md).

Note: this is a MEASUREMENT of the ceiling of the whole "better masks, keep
the classic pipeline" class. It does not build a mask.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402
import generator as G  # noqa: E402

W, H = G.DEFAULT_SIZE
COLLAPSE_FAMS = ("spiderweb", "collage", "corrosion", "cross-shadow",
                 "darts", "strippy")


def _binary_doc(ink: np.ndarray) -> Image.Image:
    """ink boolean HxW -> a soft-gray binary document the pipeline can read.

    Pure 0/255 is degenerate for the reader's own otsu (the level lands at 0
    and the mask comes out empty — measured), so ink is rendered at 25 and
    paper at 225: otsu separates them cleanly and the S8 128-150 lean band
    does not fire."""
    a = np.where(ink, 25, 225).astype(np.uint8)
    return Image.fromarray(a, "L")


def _clean_render_ink(rng) -> tuple[np.ndarray, str]:
    """Replay the shared prefix (make_label + draw_label on paper) and return
    the clean RENDER (RGB) plus its ink mask (ink is darker than paper)."""
    label = G.make_label(rng)
    img = G.draw_label(G._paper(rng, W, H), rng, label)
    a = np.array(img.convert("L"), dtype=np.int16)
    thr = (int(a.min()) + int(a.max())) // 2
    return img, a < thr, label


def oracle_overlay(rng) -> tuple[Image.Image, str]:
    """For overlay families the degradation only dims/covers — the degraded
    image minus its overlay IS the clean render. Feed that directly: the
    most faithful oracle (real paper, real ink, no synthetic gray levels)."""
    img, _, label = _clean_render_ink(rng)
    return img, label


def oracle_corrosion(rng) -> tuple[np.ndarray, str]:
    """Heavy-stroke text minus the same pits, binary."""
    label = G.make_label(rng)
    base = G._paper(rng, W, H)
    size = rng.randint(26, 40)
    font = G.load_font(rng, size)
    d = ImageDraw.Draw(base)
    bb = d.textbbox((0, 0), label, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if tw > W - 16:
        size = max(12, size * (W - 16) // tw)
        font = G.load_font(rng, size)
        bb = d.textbbox((0, 0), label, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (W - tw) // 2 - bb[0]
    y = (H - th) // 2 - bb[1]
    G._ink_color(rng)  # consumed in the original; keep the stream aligned
    for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1)):
        d.text((x + ox, y + oy), label, font=font, fill=(0, 0, 0))
    ink = np.array(base.convert("L")) < 120
    # pits: same stream as fam_corrosion
    g = G.rng_np(rng)
    n_pits = rng.randint(140, 260)
    ys, xs = np.where(ink)
    ink = ink.copy()
    if len(xs):
        for _ in range(n_pits):
            i = int(g.integers(0, len(xs)))
            px, py = int(xs[i]), int(ys[i])
            r = int(g.integers(1, 4))
            G._bg_color(rng)  # consumed in the original
            y0, y1 = max(0, py - r), min(H, py + r)
            x0, x1 = max(0, px - r), min(W, px + r)
            yy, xx = np.ogrid[y0:y1, x0:x1]
            m = (xx - px) ** 2 + (yy - py) ** 2 <= r * r
            ink[y0:y1, x0:x1][m] = False
    doc = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8), "L")
    doc = doc.filter(ImageFilter.MedianFilter(3))
    truth = np.array(doc) < 128
    return truth, label


def oracle_collage(rng) -> tuple[np.ndarray, str]:
    """Same words on white cards, same rotations/positions, binary."""
    label_words_rng = random.Random(rng.randint(0, 2 ** 62))
    words = [G.case_word(label_words_rng, label_words_rng.choice(G._WORDS))
             for _ in range(label_words_rng.randint(2, 4))]
    if label_words_rng.random() < 0.4:
        words.insert(label_words_rng.randint(1, len(words)),
                     str(label_words_rng.randint(10, 99)))
    label = " ".join(words)
    out = np.zeros((H, W), bool)
    patch = 28
    for y in range(0, H, patch):          # patchwork colors: consume rng
        for x in range(0, W, patch):
            rng.randint(150, 235)
            rng.randint(-9, 9)
            rng.randint(-9, 9)
    font_size = rng.randint(24, 34)
    font = G.load_font(rng, font_size)
    tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    widths = []
    for wd in words:
        bb = tmp.textbbox((0, 0), wd, font=font)
        widths.append(bb[2] - bb[0])
    total = sum(widths) + 14 * (len(words) - 1)
    x = max(8, (W - total) // 2 + rng.randint(-8, 8))
    rng.randint(60, 120)                  # _ink_color(randint) in original
    rng.randint(60, 120)
    rng.randint(60, 120)
    for wd, twd in zip(words, widths):
        bb = tmp.textbbox((0, 0), wd, font=font)
        th = bb[3] - bb[1]
        rng.randint(235, 250)             # card bg, consumed
        rng.randint(235, 250)
        rng.randint(230, 248)
        card = Image.new("L", (twd + 12, th + 10), 255)
        ImageDraw.Draw(card).text((6 - bb[0], 5 - bb[1]), wd, font=font,
                                  fill=0)
        ang = rng.uniform(-9, 9)
        card = card.rotate(ang, resample=Image.BICUBIC, expand=True)
        y = (H - card.height) // 2 + rng.randint(-14, 14)
        c = np.array(card) < 128
        out[y:y + c.shape[0], x:x + c.shape[1]] |= c
        x += twd + 14 + rng.randint(-4, 6)
    return out, label


ORACLES = {
    "spiderweb": oracle_overlay,
    "cross-shadow": oracle_overlay,
    "strippy": oracle_overlay,
    "darts": oracle_overlay,
    "corrosion": oracle_corrosion,
    "collage": oracle_collage,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="reports/s25-piece-gap/hard-reads.jsonl")
    ap.add_argument("--out", default="reports/s27-oracle-masks")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()


    rows = [json.loads(l) for l in open(ROOT / a.jsonl)]
    miss = [r for r in rows if not r["exact"] and r["family"] in COLLAPSE_FAMS]
    out_rows = []
    orig_family_mask = B._family_mask
    try:
        for r in miss:
            fam, idx = r["family"], int(r["id"].rsplit("-", 1)[1])
            rng = G.rng_for(fam, a.seed, idx)
            doc, label = ORACLES[fam](rng)
            assert label == r["want"], f"{r['id']}: replay label mismatch"
            if isinstance(doc, Image.Image):
                # overlay families: the clean render itself; the reader's own
                # mask stage runs unchanged on a real undegraded image
                text, _ = B.read_text(doc)
                how = "clean-render"
            else:
                # corrosion/collage: replace ONLY the mask stage with ground
                # truth; everything downstream (despeck/trim/deskew/segment/
                # match) is the unchanged read_text code path. Restore the
                # original IMMEDIATELY — a patch that outlives its item
                # contaminates every later read (that bug cost one rerun).
                truth = doc
                B._family_mask = lambda img, a, family, _t=truth: _t
                try:
                    text, _ = B.read_text(_binary_doc(truth))
                finally:
                    B._family_mask = orig_family_mask
                how = "truth-mask"
            out_rows.append({"id": r["id"], "family": fam, "want": label,
                             "oracle_got": text, "oracle_exact": text == label,
                             "oracle_how": how, "route_got": r["got"]})
    finally:
        B._family_mask = orig_family_mask
    outdir = ROOT / a.out
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / "rows.jsonl").open("w") as f:
        for r in out_rows:
            f.write(json.dumps(r) + "\n")
    from collections import defaultdict
    per = defaultdict(lambda: [0, 0])
    for r in out_rows:
        per[r["family"]][1 if r["oracle_exact"] else 0] += 1
    print(f"{'family':<14} {'misses':>6} {'oracle-exact':>12} {'still-miss':>10}")
    tot = [0, 0]
    for fam in COLLAPSE_FAMS:
        if fam not in per:
            continue
        m, e = per[fam]
        tot[0] += m
        tot[1] += e
        print(f"{fam:<14} {m + e:>6} {e:>12} {m:>10}")
    print(f"{'TOTAL':<14} {sum(tot):>6} {tot[1]:>12} {tot[0]:>10}")
    print(f"-> mask-recoverable ceiling: {tot[1]}/{sum(tot)} of the collapse-wall misses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
