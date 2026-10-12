#!/usr/bin/env python3
"""Train glyphcnn-v3 — the S16 target-class over-representation run (t-20261012-66e3).

This is the exact launcher that produced ``models/glyphcnn-v3.npz`` (trained
2026-10-12, val acc 0.9394). It is committed so the run is reproducible from a
clean clone; the recipe json it writes names the data sha and the source-file
hashes.

One-variable delta vs the committed v1/v2 recipe (``--per-class 200 --epochs 34
--generator-sheets 400``): after ``train_glyphs.build_dataset`` returns, the
target classes get ``BOOST_MULT``x extra synthetic crops (the base set already
has one copy of each; the extras bring the boosted classes to 3x total). Every
other flag, the architecture, the split, and the seed are unchanged, so v3 vs
v2 is a single-variable comparison.

Targets, from the head-tree item-level error table (2026-10-12):
  l 1 i I 0 O d            — pericles' ruled lever (S10b ruling, point 6)
  a u t R S b E T r j U L  — the measured confusable classes: a->u x5,
                             t->R x4, l->I x4, I->l x3, r->I/j x2, U->I x2,
                             S->b x2, i->1 x2, E->T x2, L->I x2

Usage (from a clean clone):
    python3 tools/train_v3_targets.py                 # writes models/glyphcnn-v3.npz
    python3 tools/train_v3_targets.py --data /tmp/d.npz   # dataset cache path

No reader, gate, or recipe file is touched. The swap-in of v3 behind the
existing glyphcnn gate is a separate decision (barry/pericles).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import train_glyphs as T  # noqa: E402

BOOST = set("l1iI0Od") | set("autRESbjUL")
BOOST_MULT = 3  # total multiplier for boosted classes (1 base + 2 extra)

_orig_build_dataset = T.build_dataset


def build_dataset_boosted(per_class: int, seed: int, size_px: int = 24,
                          verbose: bool = True):
    x, y = _orig_build_dataset(per_class, seed, size_px, verbose)
    rng = np.random.default_rng(seed + 777)
    fonts = T.available_fonts()
    extra_x, extra_y = [], []
    for ci, ch in enumerate(T.CHARS):
        if ch not in BOOST:
            continue
        for _ in range(per_class * (BOOST_MULT - 1)):
            a = np.zeros((1, size_px, size_px), dtype=np.float32)
            a[0] = T.render_crop(ch, rng, fonts, size_px)
            extra_x.append(a)
            extra_y.append(ci)
    if extra_x:
        x = np.concatenate([x, np.stack(extra_x)], axis=0)
        y = np.concatenate([y, np.array(extra_y, dtype=np.int64)])
    if verbose:
        print(f"v3 boost: +{len(extra_y)} crops for {len(BOOST)} classes "
              f"({BOOST_MULT}x)")
    return x, y


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "models" / "glyphcnn-v3.npz"))
    ap.add_argument("--data", default=str(ROOT / "data" / "glyphs-v3.npz"),
                    help="dataset cache path (contents are seed-reproducible)")
    args = ap.parse_args()

    T.build_dataset = build_dataset_boosted
    sys.argv = [
        "train_glyphs.py",
        "--per-class", "200", "--epochs", "34", "--generator-sheets", "400",
        "--out", args.out,
        "--data", args.data,
    ]
    rc = T.main()
    return rc if isinstance(rc, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
