#!/usr/bin/env python3
"""S24 probe (t-20261012-c4af, marcus): can glyphcnn-v3 decide letter CASE
from a normalized crop?

The S24 report proposes case re-scoring from pixels for the 9/10 iris hard
residuals stuck in the case lane. This measures the FIRST step of that
proposal: the crop-level case-discrimination ceiling of the committed CNN.

Method: render K deterministic crops per class with the training renderer
(tools/train_glyphs.render_crop — same fonts, same bbox normalisation the
model was trained on), predict, and report per case-twin pair:
P(correct | upper), P(correct | lower), and confusion into the twin.

Run:  python3 tools/s24_case_probe.py [--weights models/glyphcnn-v3.npz]
                                      [--k 24] [--seed 7]
Offline, stdlib+numpy+Pillow, ~2 s per 26 pairs at K=24.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "readers"))

from train_glyphs import available_fonts, render_crop  # noqa: E402
from glyphcnn import CHARS, GlyphCNN  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="models/glyphcnn-v3.npz")
    ap.add_argument("--k", type=int, default=24, help="crops per class")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--min-acc", type=float, default=0.8,
                    help="threshold for 'case-decidable'")
    a = ap.parse_args()

    net = GlyphCNN(init_from=dict(np.load(ROOT / a.weights)))
    fonts = available_fonts()
    rng = np.random.default_rng(a.seed)

    print(f"weights: {a.weights} | fonts: {len(fonts)} | K={a.k} | seed={a.seed}")
    print(f"{'pair':6} {'P(up|up)':>9} {'->low':>6} {'P(low|low)':>10} {'->up':>6}")
    decidable = 0
    weak = []
    for cu in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        cl = cu.lower()
        accs = {}
        for ch in (cu, cl):
            yi = CHARS.index(ch)
            twin = CHARS.index(cl if ch == cu else cu)
            x = np.zeros((a.k, 1, 24, 24), dtype=np.float32)
            for i in range(a.k):
                x[i, 0] = render_crop(ch, rng, fonts, 24)
            pred = net.predict(x)
            accs[ch] = ((pred == yi).mean(), (pred == twin).mean())
        (uc, ut), (lc, lt) = accs[cu], accs[cl]
        ok = uc >= a.min_acc and lc >= a.min_acc
        decidable += ok
        flag = "" if ok else "  <-- weak"
        if not ok:
            weak.append(f"{cu}/{cl} (up {uc:.2f}, low {lc:.2f})")
        print(f"{cu}/{cl:4} {uc:9.2f} {ut:6.2f} {lc:10.2f} {lt:6.2f}{flag}")

    print(f"\ncase-decidable pairs (>={a.min_acc:.0%} both ways): {decidable}/26")
    if weak:
        print("weak pairs:", ", ".join(weak))
    print("\nCAVEAT: synthetic crops from the training renderer. Real suite "
          "crops pass degradation + segmentation first; the next measurement "
          "is this probe on crops cut from actual suite items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
