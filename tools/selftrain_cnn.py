#!/usr/bin/env python3
"""tools/selftrain_cnn.py — S6 phase 3: self-train on unlabelled hard
images (t-20261011-00c0).

Phase 1 (combine) gave +1.6 exact points, phase 2 (augmentation search)
+5.4 — all far under the bar. The last lever the task cards: use the
UNLABELLED hard images. Procedure, honestly measured:

  1. generate K hard images per family with seed S_train; the generator
     must label them, but the labels are DISCARDED before training
     (kept only for the audit line below, never fit()'ed);
  2. segment + classify every glyph crop with the committed CNN; keep
     crops whose max softmax probability >= --threshold as pseudo-labels;
  3. fine-tune a COPY of the net on pseudo-labels only;
  4. re-read a held-out, LABELLED suite (seed --seed-eval, the same seed
     the phase-1/2 tables use) with base net and fine-tuned net and print
     the delta. easy is evaluated too — a hard-only gain that breaks
     easy would be a regression, and the report says so.

Auditing honesty: for boxes whose count matches the true label, the audit
line counts how many pseudo-labels were actually right. If the pipeline
teaches itself garbage, this number says it.

    python3 tools/selftrain_cnn.py --per-family 12 --seed-eval 7 \
        --out reports/selftrain.json [--save models/glyphcnn-selftrain.npz]

Only pass --save when the delta is a real gain; otherwise the fine-tuned
weights are a report artifact, not a product.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generator as G  # noqa: E402
from readers.glyphcnn import GlyphCNN, char_to_index, index_to_char  # noqa: E402
from readers.segmentation import analyse, normalise_glyph  # noqa: E402


def read_img(img, net) -> str:
    mask, boxes = analyse(img.convert("RGB"))
    if not boxes:
        return ""
    crops = np.stack([normalise_glyph(mask, box) for box, _ in boxes])[:, None, :, :]
    probs = net.forward(crops.astype(net.p["w1"].dtype))[0]
    out = []
    for i, (_, space_before) in enumerate(boxes):
        ch = index_to_char(int(probs[i].argmax()))
        if space_before and out and out[-1] != " ":
            out.append(" ")
        out.append(ch)
    return "".join(out)


def evaluate(net, fams, count, seed) -> dict:
    rows = {}
    for fam in fams:
        exact = 0
        for i in range(count):
            img, label = G.generate_one(fam, seed=seed, index=i)
            exact += read_img(img, net) == label
        rows[fam] = round(exact / count, 4)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-family", type=int, default=12, help="unlabelled train images/family")
    ap.add_argument("--seed-train", type=int, default=71)
    ap.add_argument("--threshold", type=float, default=0.92)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--eval-count", type=int, default=10)
    ap.add_argument("--seed-eval", type=int, default=7)
    ap.add_argument("--families", default="")
    ap.add_argument("--out", help="json report path")
    ap.add_argument("--save", help="write fine-tuned weights here")
    args = ap.parse_args()

    hard = [f for f in (args.families.split(",") if args.families else G.FAMILIES) if f != "easy"]
    base = GlyphCNN.load(str(ROOT / "models" / "glyphcnn.npz"))

    # ---- phase A: pseudo-label collection (labels discarded for training)
    t0 = time.time()
    xs, ys = [], []
    kept = seen = 0
    audited = audited_ok = 0
    for fam in hard:
        for i in range(args.per_family):
            img, label = G.generate_one(fam, seed=args.seed_train, index=i)
            mask, boxes = analyse(img.convert("RGB"))
            if not boxes:
                continue
            crops = np.stack([normalise_glyph(mask, box) for box, _ in boxes])[:, None, :, :]
            probs = base.forward(crops.astype(base.p["w1"].dtype))[0]
            true = [c for c in label if c != " "]
            align = len(true) == len(boxes)
            for j, (box, _) in enumerate(boxes):
                seen += 1
                p = float(probs[j].max())
                if p < args.threshold:
                    continue
                kept += 1
                xs.append(crops[j, 0])
                ys.append(char_to_index(index_to_char(int(probs[j].argmax()))))
                if align:
                    audited += 1
                    audited_ok += int(ys[-1] == char_to_index(true[j]))
    collect_s = round(time.time() - t0, 1)
    print(f"pseudo-labels: kept {kept}/{seen} glyphs (thr {args.threshold}); "
          f"audit: {audited_ok}/{audited} pseudo-labels actually correct "
          f"({(audited_ok/audited*100 if audited else 0):.1f}%) | {collect_s}s")

    # ---- phase B: fine-tune on pseudo-labels only
    if kept:
        x = np.stack(xs).astype(np.float32)[:, None, :, :]
        y = np.array(ys, dtype=np.int64)
        tuned = GlyphCNN(init_from={k: v.copy() for k, v in base.p.items()})
        t0 = time.time()
        hist = tuned.fit(x, y, epochs=args.epochs, lr=args.lr, lr_end=args.lr / 5,
                         batch=128, seed=3, verbose=True)
        fit_s = round(time.time() - t0, 1)
        print(f"fine-tune: {args.epochs} epochs on {kept} glyphs | loss "
              f"{hist[0][1]:.4f} -> {hist[-1][1]:.4f} | {fit_s}s")
    else:
        tuned, fit_s, hist = base, 0.0, []
        print("no pseudo-labels above threshold — nothing to fit; tuned == base")

    # ---- phase C: held-out evaluation, base vs tuned
    fams_eval = ["easy"] + hard
    t0 = time.time()
    before = evaluate(base, fams_eval, args.eval_count, args.seed_eval)
    after = evaluate(tuned, fams_eval, args.eval_count, args.seed_eval)
    eval_s = round(time.time() - t0, 1)
    mean_b = sum(before.values()) / len(before)
    mean_a = sum(after.values()) / len(after)
    report = {
        "threshold": args.threshold, "per_family_train": args.per_family,
        "seed_train": args.seed_train, "seed_eval": args.seed_eval,
        "eval_count": args.eval_count,
        "pseudo": {"kept": kept, "seen": seen,
                   "audit_correct": audited_ok, "audit_total": audited,
                   "audit_frac": round(audited_ok / audited, 4) if audited else None},
        "fit": {"epochs": args.epochs, "lr": args.lr,
                "loss_first": round(hist[0][1], 4) if hist else None,
                "loss_last": round(hist[-1][1], 4) if hist else None},
        "exact_before": before, "exact_after": after,
        "mean_before": round(mean_b, 4), "mean_after": round(mean_a, 4),
        "delta_points": round((mean_a - mean_b) * 100, 1),
        "seconds": {"collect": collect_s, "fit": fit_s, "eval": eval_s},
    }
    print(f"held-out exact (seed {args.seed_eval}, {args.eval_count}/family), base -> tuned:")
    for fam in fams_eval:
        d = (after[fam] - before[fam]) * 100
        print(f"    {fam:<14} {before[fam]*100:5.0f}% -> {after[fam]*100:5.0f}%  ({d:+.0f})")
    print(f"    mean           {mean_b*100:5.1f}% -> {mean_a*100:5.1f}%  "
          f"({report['delta_points']:+.1f} points)")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")
    if args.save and kept:
        tuned.save(args.save)
        print(f"fine-tuned weights -> {args.save}")


if __name__ == "__main__":
    main()
