#!/usr/bin/env python3
"""s10_diagnose.py — where does the glyph CNN lose? (S10, t-20261012-4447)

Evaluates a trained glyph CNN on the SAME stratified val split the training
recipe uses, then prints, in order of usefulness for fixing it:

  1. overall val accuracy (sanity vs the recipe's recorded number),
  2. the worst classes by accuracy, with their top confusions (who steals them),
  3. case-pair leakage (o/O, c/C, s/S ... the classic failure mode here),
  4. confidence-gate calibration: for thresholds t, how many val glyphs pass
     t and how accurate the passed set is — the numbers the confidence-gated
     reader chain needs to pick its gate honestly.

Usage:
    python3 tools/s10_diagnose.py --data /tmp/s10-data.npz \
        --model models/glyphcnn.npz [--json /tmp/s10-diagnosis.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))
sys.path.insert(0, str(ROOT / "tools"))

from glyphcnn import CHARS, GlyphCNN  # noqa: E402
import train_glyphs as TG  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(ROOT / "data" / "glyphs.npz"))
    ap.add_argument("--model", default=str(ROOT / "models" / "glyphcnn.npz"))
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    with np.load(args.data) as d:
        x, y = d["x"], d["y"]
    _, _, xva, yva = TG.stratified_split(x, y)
    net = GlyphCNN.load(args.model)
    probs = net.forward(xva.astype(np.float32))[0]
    preds = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    acc = float((preds == yva).mean())
    print(f"val: {len(yva)} glyphs | acc {acc:.4f} | dataset {args.data} | model {args.model}")

    # per-class + confusions
    per_class = []
    for ci, ch in enumerate(CHARS):
        m = yva == ci
        n = int(m.sum())
        if not n:
            continue
        ok = int((preds[m] == ci).sum())
        wrong = preds[m][preds[m] != ci]
        top = []
        if len(wrong):
            vals, cnts = np.unique(wrong, return_counts=True)
            order = np.argsort(-cnts)[:3]
            top = [(CHARS[int(vals[i])], int(cnts[i])) for i in order]
        per_class.append({"char": ch, "n": n, "acc": ok / n, "confused_with": top})

    worst = sorted(per_class, key=lambda r: (r["acc"], -r["n"]))[: args.top]
    print("\nworst classes (char, acc, n, who steals):")
    for r in worst:
        steal = ", ".join(f"{c}x{k}" for c, k in r["confused_with"]) or "-"
        print(f"  {r['char']!r}: {r['acc']*100:5.1f}%  n={r['n']:3d}  {steal}")

    # case-pair leakage
    pairs = []
    for lo in "abcdefghijklmnopqrstuvwxyz":
        up = lo.upper()
        if up not in CHARS:
            continue
        m = (yva == CHARS.index(lo)) | (yva == CHARS.index(up))
        if not m.any():
            continue
        leak = int((preds[m] != yva[m]).sum())
        cross = int(sum(1 for p, t in zip(preds[m], yva[m])
                        if CHARS[p] in (lo, up) and CHARS[p] != CHARS[t]))
        pairs.append({"pair": lo + up, "n": int(m.sum()), "wrong": leak, "case_cross": cross})
    cross_total = sum(p["case_cross"] for p in pairs)
    wrong_total = int((preds != yva).sum())
    print(f"\ncase-pair leakage: {cross_total}/{wrong_total} errors cross case "
          f"({cross_total / max(wrong_total, 1) * 100:.1f}% of all errors)")
    for p in sorted(pairs, key=lambda r: -r["case_cross"])[:8]:
        if p["case_cross"]:
            print(f"  {p['pair']}: {p['case_cross']}/{p['n']} cross-case errors")

    # confidence-gate calibration
    gates = []
    print("\nconfidence gate (the numbers the reader chain needs):")
    for t in (0.5, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99):
        keep = conf >= t
        if not keep.any():
            gates.append({"t": t, "kept": 0, "kept_frac": 0.0, "acc": None})
            print(f"  p>={t:.2f}: kept 0")
            continue
        kacc = float((preds[keep] == yva[keep]).mean())
        gates.append({"t": t, "kept": int(keep.sum()),
                      "kept_frac": float(keep.mean()), "acc": kacc})
        print(f"  p>={t:.2f}: kept {keep.mean()*100:5.1f}% of glyphs, "
              f"accuracy on kept {kacc*100:.2f}%")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "data": args.data, "model": args.model, "val_n": int(len(yva)),
            "val_acc": acc, "worst": worst, "case_pairs": pairs,
            "case_cross_of_errors": cross_total / max(wrong_total, 1),
            "gates": gates}, indent=1))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
