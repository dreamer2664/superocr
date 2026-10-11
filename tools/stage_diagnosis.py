#!/usr/bin/env python3
"""tools/stage_diagnosis.py — crack the zero-wall families (t-20261011-be57).

reports/s6-summary.md showed collage, corrosion, cross-shadow, darts and
dark-on-dark at 0% exact under the floor, all augmentations, the CNN and
self-training. Before touching the reader, attribute the failure to a
STAGE, per family, with numbers. Same images, seeds and counts as the
floor report (seed 7, 10/family).

  stage B  binarisation: mask ink mass after otsu+despeck (empty mask =
           the read was over before it started)
  stage S  segmentation: pieces after word-split + guards vs the true
           glyph count (under = collapsed boxes, over = junk/split marks
           surviving guards)
  stage C  classification: on images where pieces == true glyphs, how
           often the produced string is still wrong — a pure matcher loss

A second segmenter opinion (readers.segmentation.analyse, now on main)
is counted alongside so "baseline-only blindness" is visible too.

    python3 tools/stage_diagnosis.py --out reports/stage-diagnosis.json
"""
from __future__ import annotations

import argparse
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

try:
    from readers.segmentation import analyse as cnn_analyse  # noqa: E402
    CNN_OK = True
except Exception:  # pragma: no cover
    CNN_OK = False

ZERO_WALL = ["collage", "corrosion", "cross-shadow", "darts", "dark-on-dark"]


def baseline_mask(img: Image.Image) -> np.ndarray:
    """The floor's own binarisation path, up to (and incl.) deskew."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.trim(R.despeck(R.otsu(a)))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    return mask


def count_pieces(mask: np.ndarray) -> int:
    """The floor's own segmentation path (words, split_wide, guards)."""
    n = 0
    for word in R.segment(mask):
        for x0, x1 in word:
            for g in R.split_wide(R.trim(mask[:, x0:x1])):
                if g.shape[0] >= 6 and g.sum() >= 10:
                    n += 1
    return n


def _char_acc(label: str, text: str) -> float:
    l1, l2 = label.replace(" ", ""), text.replace(" ", "")
    tot = max(len(l1), len(l2)) or 1
    return sum(a == b for a, b in zip(l1, l2)) / tot


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--families", default=",".join(ZERO_WALL))
    ap.add_argument("--out", help="json report path")
    args = ap.parse_args()

    fams = [f for f in args.families.split(",") if f]
    t0 = time.time()
    rows = []
    for fam in fams:
        m = dict(empty_mask=0, true=0, pieces=0, cnn_boxes=0, exact=0,
                 seg_ok=0, seg_ok_but_wrong=0, char_sum=0.0)
        for i in range(args.count):
            img, label = G.generate_one(fam, seed=args.seed, index=i)
            true = len(label.replace(" ", ""))
            text, conf = B.read_text(img)
            mask = baseline_mask(img)
            pieces = count_pieces(mask)
            m["empty_mask"] += not mask.any()
            m["true"] += true
            m["pieces"] += pieces
            if CNN_OK:
                _, boxes = cnn_analyse(img.convert("RGB"))
                m["cnn_boxes"] += len(boxes)
            m["exact"] += text == label
            m["seg_ok"] += pieces == true
            m["seg_ok_but_wrong"] += (pieces == true and text != label)
            m["char_sum"] += _char_acc(label, text)
        n = args.count
        rows.append({
            "family": fam,
            "true_glyphs": m["true"],
            "empty_mask_frac": round(m["empty_mask"] / n, 2),
            "pieces_per_true": round(m["pieces"] / m["true"], 3),
            "cnn_boxes_per_true": round(m["cnn_boxes"] / m["true"], 3) if CNN_OK else None,
            "seg_count_ok_frac": round(m["seg_ok"] / n, 2),
            "cls_fail_when_seg_ok": round(m["seg_ok_but_wrong"] / m["seg_ok"], 2) if m["seg_ok"] else None,
            "exact": round(m["exact"] / n, 2),
            "char": round(m["char_sum"] / n, 3),
        })

    report = {"seed": args.seed, "count": args.count,
              "families": rows, "seconds": round(time.time() - t0, 1),
              "cnn_segmenter": CNN_OK}
    print(f"stage diagnosis — seed {args.seed}, {args.count}/family, {report['seconds']}s")
    print(f"{'family':<14}{'ink?':>6}{'seg/true':>9}{'cnn/true':>9}{'segOK':>7}"
          f"{'clsFail|segOK':>14}{'exact':>7}{'char':>7}")
    for r in rows:
        cnn = f"{r['cnn_boxes_per_true']:.2f}" if r['cnn_boxes_per_true'] is not None else "n/a"
        cf = "—" if r["cls_fail_when_seg_ok"] is None else f"{r['cls_fail_when_seg_ok']:.2f}"
        print(f"{r['family']:<14}{1-r['empty_mask_frac']:>6.2f}{r['pieces_per_true']:>9.2f}"
              f"{cnn:>9}{r['seg_count_ok_frac']:>7.2f}{cf:>14}"
              f"{r['exact']:>7.2f}{r['char']:>7.3f}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")


if __name__ == "__main__":
    main()
