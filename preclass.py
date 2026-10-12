#!/usr/bin/env python3
"""preclass — the cheap pre-classifier behind auto mode (t-20261012-5c63).

Auto mode used to run ALL thirteen family chains and return the best average
confidence. Measured on the official probes (tools/demo_latency.py pictures,
seeds pinned) that is 9.7 s on the easy probe, 15.9 s on split, 46.8 s on
strippy — against the 10 s bar in JOBS.md — and the argmax over confidence
picked the true family on only 2 of 6 probes, because the reader's glyph
confidence is not calibrated across families (garbage masks score ~0.7 too).

This module computes a handful of cheap pixel statistics (native resolution,
no downscaling: the telling structure is 1-6 px wide) and returns a SHORTLIST
of families that look plausible for this image. Auto then runs only those
chains. The statistics are structural, matched to what each family's
generator actually does:

  darkfrac   everything lives near black            -> dark-on-dark
  speck      saturated 1-px specks on ordinary paper -> snow
  strobe     row-median paper tone as a square wave  -> strippy
  grey_far   lots of grey structure away from ink    -> collage
  split_margin  one coherent >=8 px half-shift       -> split (and stitch)
  midgrey    soft mid-tone patches over clean paper  -> obstruction / darts / web
  tone       mean tone + midgrey band                -> cross-shadow

Honesty rules for this file: it ROUTES, it does not read. It makes no
accuracy claim about the reader. Every threshold below was picked from
measurements on generator output (tools/measure_preclass.py prints the
per-family confusion on HELD-OUT seeds), the shortlist always keeps `easy`
as the cheap safety reading, and it never widens beyond four families, so
auto stays inside the 10 s bar. `--family all` still runs the old full
scan for anyone who wants it.

Thresholds were set with margin against the measured spread; the numbers
are in reports/s9-latency.md (per-family, held-out).
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _work(img: Image.Image) -> np.ndarray:
    """Native-resolution grayscale. No downscale: speckle/pits/seams are px-scale."""
    return np.asarray(img.convert("L"), dtype=np.float32)


def _box(m: np.ndarray, r: int = 2) -> np.ndarray:
    """Mean of a boolean mask over a (2r+1)^2 window (summed-area table)."""
    c = np.pad(m.astype(np.float32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    H, W = m.shape
    y0 = np.clip(np.arange(H) - r, 0, H); y1 = np.clip(np.arange(H) + r + 1, 0, H)
    x0 = np.clip(np.arange(W) - r, 0, W); x1 = np.clip(np.arange(W) + r + 1, 0, W)
    S = c[np.ix_(y1, x1)] - c[np.ix_(y0, x1)] - c[np.ix_(y1, x0)] + c[np.ix_(y0, x0)]
    area = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    return S / area


def _ncc_shift(p: np.ndarray, q: np.ndarray, span: int = 26) -> dict:
    """Normalised cross-correlation of row profiles p, q at every shift."""
    n = len(p)
    out = {}
    for d in range(-span, span + 1):
        if d >= 0:
            A, B = p[:n - d], q[d:]
        else:
            A, B = p[-d:], q[:n + d]
        if A.size < 10:
            continue
        den = np.linalg.norm(A) * np.linalg.norm(B)
        if den > 1e-6:
            out[d] = float(np.dot(A, B) / den)
    return out


# --------------------------------------------------------------------------
# the statistics
# --------------------------------------------------------------------------

def stats(img: Image.Image) -> dict:
    a = _work(img)
    H, W = a.shape
    p2, p98 = np.percentile(a, (2, 98))
    paper_tone = float(np.median(a))
    span = float(p98 - p2)
    dark = a < paper_tone - max(25.0, 0.20 * span)     # ink-ish
    paper = a > paper_tone - 15                        # the sheet itself
    f: dict[str, float] = {}

    # tone
    f["mean"] = float(a.mean() / 255.0)
    f["darkfrac"] = float((a < 60).mean())
    f["midgrey"] = float(((a >= 62) & (a < 208)).mean())
    f["grey_far"] = 0.0

    # snow: saturated specks whose 3x3 median is ordinary paper
    u8 = Image.fromarray(a.astype(np.uint8))
    med3 = np.asarray(u8.filter(ImageFilter.MedianFilter(3)), dtype=np.float32)
    f["speck"] = float(((a >= 250) & (med3 < 240)).mean())

    # strippy: the row-median paper tone alternates like a square wave
    rm = np.median(a, axis=1)
    rm = rm - rm.mean()
    worst = 0.0
    for lag in range(5, 16):
        x, y = rm[:-lag], rm[lag:]
        den = np.linalg.norm(x) * np.linalg.norm(y)
        if den > 1e-6:
            worst = min(worst, float(np.dot(x, y) / den))
    f["strobe"] = -worst

    # collage / overlays: grey structure away from the ink (dilate the ink a little)
    ink_dil = _box(dark, 3) > 0.02
    grey = (a > 62) & (a < 208) & ~ink_dil
    f["grey_far"] = float(grey.mean())

    # split / stitch: coherent vertical displacement between the two halves
    best_big, best_margin = 0.0, -2.0
    for x in range(int(0.30 * W), int(0.70 * W), 6):
        p = dark[:, :x].sum(axis=1).astype(np.float32)
        q = dark[:, x:].sum(axis=1).astype(np.float32)
        cc = _ncc_shift(p, q)
        if not cc:
            continue
        big = max([v for d, v in cc.items() if abs(d) >= 8], default=-2.0)
        small = max([v for d, v in cc.items() if abs(d) <= 3], default=-2.0)
        best_big = max(best_big, big)
        best_margin = max(best_margin, big - small)
    f["split_margin"] = best_margin
    f["split_big"] = best_big

    return f


# --------------------------------------------------------------------------
# the shortlist
# --------------------------------------------------------------------------

# fixed tie-break order, cheapest-first where scores are equal
_ORDER = ["dark-on-dark", "snow", "strippy", "collage", "split", "stitch",
          "obstruction", "cross-shadow", "darts", "spiderweb", "easy"]


def shortlist(img: Image.Image) -> tuple[list[str], dict]:
    """Families worth running for this image, most plausible first.

    A signal that fires strongly (score >= 2) stands alone next to `easy`:
    running anything else would only add seconds, not evidence. Weaker
    signals widen the list to at most three families. `easy` always rides
    along as the cheap safety reading, and an image that matches nothing
    just gets `easy` -- the same reading the old full scan returned most
    often on such images, minus the wait.
    """
    f = stats(img)
    cands: list[tuple[str, float]] = []

    if f["darkfrac"] > 0.40:
        cands.append(("dark-on-dark", f["darkfrac"] / 0.40))
    if f["speck"] > 0.008:
        cands.append(("snow", f["speck"] / 0.008))
    if f["strobe"] > 0.13:
        cands.append(("strippy", f["strobe"] / 0.13))
    if f["grey_far"] > 0.10:
        cands.append(("collage", f["grey_far"] / 0.10))
    if f["split_margin"] > 0.45:
        cands.append(("split", f["split_margin"] / 0.45))
    elif f["split_margin"] > 0.28:
        # a real displacement, but not decisively one half-shift: both readers
        cands.append(("split", 0.9))
        cands.append(("stitch", 0.9))
    if 0.020 < f["midgrey"] <= 0.20 and f["mean"] > 0.85:
        # soft mid-tone structure over otherwise clean paper: the three
        # overlay families, plus cross-shadow (its bands sit in the band too)
        cands.append(("obstruction", f["midgrey"] / 0.03))
        cands.append(("cross-shadow", f["midgrey"] / 0.12))
        cands.append(("darts", f["midgrey"] / 0.04))
        cands.append(("spiderweb", f["midgrey"] / 0.05))
    elif f["midgrey"] > 0.14:
        cands.append(("cross-shadow", f["midgrey"] / 0.14))

    rank = {name: i for i, name in enumerate(_ORDER)}
    cands.sort(key=lambda kv: (-kv[1], rank.get(kv[0], 99)))
    strong = bool(cands) and cands[0][1] >= 2.0
    if strong:
        picked = [cands[0][0]]
    else:
        picked = [name for name, _ in cands[:3]]
    if "easy" not in picked:
        picked.append("easy")
    info = {"stats": {k: round(v, 4) for k, v in f.items()},
            "cands": [(n, round(sc, 2)) for n, sc in cands],
            "strong": strong}
    return picked[:4], info
