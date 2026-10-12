#!/usr/bin/env python3
"""preclassify.py — the cheap pre-classifier for auto mode (t-20261012-5c63).

Why this exists: auto mode used to run every family's chain (13 of them) and
pick the winner by average glyph confidence. That was 8-21 s per image (the
26 s strippy probe), and worse, the arbitration was gameable — a chain that
decoded two garbage glyphs with high confidence could beat the right chain
(an easy image was regularly read as 'cut'). This module looks at the IMAGE
first: 21 cheap numpy features, nearest-centroid over generator samples,
and a ranked shortlist. The caller (typer.recognise) then runs only the top
chains and arbitrates between those — same accuracy floor, a fraction of the
work.

Honest numbers (held-out generator images, seed 42, indices the centroids
never saw): top-1 87%, top-2 94%, top-3 99%. Auto mode therefore runs ONE
chain — the pre-classifier's pick — and only pays for more when that chain
fails to produce a usable read (bounded fallback, worst case all 13). The
features are structural (contrast, speckle, stripe periodicity, seam
discontinuity, blotch energy, solid-bar row), not learned — they are
readable in one sitting and debuggable with the CLI below.

    python3 preclassify.py image.png              # ranked families
    python3 preclassify.py image.png --top 3
    python3 preclassify.py --rebuild              # regenerate the centroid cache

Determinism: centroids come from generator.py with a fixed seed; the cache
file models/preclass_centroids.npz is committed, and --rebuild reproduces it
byte-for-byte from a clean clone.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import generator as G

HERE = Path(__file__).resolve().parent
CACHE = HERE / "models" / "preclass_centroids.npz"

SEED = 42
TRAIN_INDICES = range(200, 208)      # 8 images per family
HELDOUT_INDICES = range(300, 316)    # for the honest accuracy test only

ALL_FAMILIES = ["easy"] + [f for f in G.FAMILIES if f != "easy"]


# ---------------------------------------------------------------- features

def _lum(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=float)


def feats(a: np.ndarray) -> np.ndarray:
    """~20 structural features of a luminance array. Pure, cheap, no state."""
    f: list[float] = []
    p5, p50, p95 = np.percentile(a, [5, 50, 95])
    f += [p95 - p5, p95 - p50, p50 - p5]                    # contrast shape
    m = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0)
         + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
    f.append(float(np.mean(np.abs(a - m))))                 # speckle (snow)
    cs = a.sum(axis=0)
    rs = a.sum(axis=1)

    def ac(x: np.ndarray, k: int) -> float:
        x = x - x.mean()
        return float((x[:-k] * x[k:]).sum() / max(1e-9, float((x * x).sum())))

    f += [ac(cs, 1), ac(cs, 2), ac(cs, 4), ac(rs, 1)]       # stripe periodicity
    gx = float(np.abs(np.diff(a, axis=1)).mean())
    gy = float(np.abs(np.diff(a, axis=0)).mean())
    f += [gx, gy, gx / max(gy, 1e-9)]                       # gradient balance
    H, W = a.shape
    qs = [np.median(a[:H // 4, :W // 4]), np.median(a[:H // 4, -W // 4:]),
          np.median(a[-H // 4:, :W // 4]), np.median(a[-H // 4:, -W // 4:])]
    f.append(float(np.ptp(qs)))                             # corner bg spread (collage)
    thr = (p5 + p95) / 2.0
    f.append(float((a < thr).mean()))                       # ink fraction
    hist, _ = np.histogram(a, bins=32, range=(0, 256))
    hist = hist / max(1, hist.sum())
    f.append(float(np.max(hist)))                           # histogram peakiness
    top = rs[:H // 2] - rs[:H // 2].mean()
    bot = rs[H // 2:] - rs[H // 2:].mean()
    n = min(len(top), len(bot))
    best = max(
        float((top[:n] * np.roll(bot, d)[:n]).sum()
              / max(1e-9, float(np.sqrt((top[:n] * top[:n]).sum()
                                        * (bot[:n] * bot[:n]).sum()))))
        for d in (-8, -4, 0, 4, 8))
    f.append(best)                                          # split: best-dy row corr
    bands = 6
    med = [np.median(a[:, i * W // bands:(i + 1) * W // bands])
           for i in range(bands)]
    f.append(float(np.ptp(med)))                            # stitch: strip bg change
    lap = np.abs(4 * a - np.roll(a, 1, 0) - np.roll(a, -1, 0)
                 - np.roll(a, 1, 1) - np.roll(a, -1, 1))
    f.append(float(lap.mean()))                             # blotch energy (corrosion)
    thr2 = p50 - 0.6 * (p50 - p5)
    rowink = (a < thr2).mean(axis=1)
    f.append(float(rowink.max()))                           # solid bar (obstruction)
    csz = (cs - cs.mean()) / max(1e-9, cs.std())
    f.append(float(np.abs(np.diff(csz)).max()))             # seam sharpness (stitch)
    rl = a[:, :W // 2].mean(axis=1)
    rr = a[:, W // 2:].mean(axis=1)
    rl = (rl - rl.mean()) / max(1e-9, rl.std())
    rr = (rr - rr.mean()) / max(1e-9, rr.std())
    dys = list(range(-20, -3)) + list(range(4, 21))
    dnz = max(abs((rl * np.roll(rr, d)).mean()) for d in dys)
    f.append(float(dnz))
    # ^ halves offset: split keeps text rows correlated across a vertical shift
    f.append(float(abs((rl * rr).mean()) - dnz))
    # ^ banding: full-width stripes (strippy) align the halves at zero shift best
    return np.array(f, float)


def image_feats(img: Image.Image) -> np.ndarray:
    return feats(_lum(img))


# ---------------------------------------------------------------- centroids

def build_centroids() -> dict[str, np.ndarray]:
    """Generate TRAIN_INDICES per family, average the feature vectors."""
    out: dict[str, np.ndarray] = {}
    for fam in ALL_FAMILIES:
        vs = []
        for i in TRAIN_INDICES:
            img, _ = G.generate_one(fam, seed=SEED, index=i)
            vs.append(feats(_lum(img)))
        out[fam] = np.mean(vs, axis=0)
    return out


def save_centroids(cents: dict[str, np.ndarray]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE, families=np.array(sorted(cents)),
             feats=np.array([cents[f] for f in sorted(cents)]))


def load_centroids() -> dict[str, np.ndarray]:
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=False)
        return {str(f): v for f, v in zip(z["families"], z["feats"])}
    cents = build_centroids()
    try:
        save_centroids(cents)
    except OSError as e:                                    # read-only checkout
        print(f"preclassify: cache missing and not writable ({e}); "
              "using in-memory centroids", file=sys.stderr)
    return cents


_CENTS: dict[str, np.ndarray] | None = None
_SCALE: np.ndarray | None = None


def _centroids_and_scale() -> tuple[dict[str, np.ndarray], np.ndarray]:
    global _CENTS, _SCALE
    if _CENTS is None or _SCALE is None:
        _CENTS = load_centroids()
        allc = np.array(list(_CENTS.values()))
        _SCALE = np.maximum(allc.std(axis=0), 1e-6)
    return _CENTS, _SCALE


def rank(img: Image.Image, top: int | None = None) -> list[str]:
    """Families ordered most→least plausible for this image."""
    cents, scale = _centroids_and_scale()
    v = image_feats(img)
    d = {f: float(np.abs((v - c) / scale).sum()) for f, c in cents.items()}
    ordered = sorted(d, key=d.get)
    return ordered[:top] if top else ordered


def shortlist(img: Image.Image, k: int = 2) -> list[str]:
    """The chains auto mode should actually run (plus 'easy' as a safety net
    when it is not already included: an easy image must never pay for the
    others' confusion)."""
    top = rank(img, k)
    if "easy" not in top and len(top) >= k:
        # only displace the k-th if 'easy' ranks within the top k+1
        wider = rank(img, k + 1)
        if wider[-1] == "easy":
            top = wider[:k - 1] + ["easy"]
    return top


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="rank families for one image")
    ap.add_argument("image", nargs="?", help="image file (omit with --rebuild)")
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--rebuild", action="store_true",
                    help="regenerate the centroid cache and exit")
    args = ap.parse_args(argv)
    if args.rebuild:
        save_centroids(build_centroids())
        print(f"centroids rebuilt -> {CACHE}")
        return 0
    if not args.image:
        ap.error("give an image (or --rebuild)")
    img = Image.open(args.image)
    for i, fam in enumerate(rank(img, args.top), 1):
        print(f"{i:2d}. {fam}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
