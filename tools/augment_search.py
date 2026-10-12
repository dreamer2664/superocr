#!/usr/bin/env python3
"""tools/augment_search.py — S6 phase 2: search augmentations (t-20261011-00c0).

The classic floor precedes reading with one fixed binarisation. Phase 1
showed best-of-3 readers gains almost nothing (13.1% vs 11.5% floor), so
the next honest knob is the IMAGE, not the reader: try a small, fixed set
of deterministic pre-read augmentations and let the floor reader re-read.

    python3 tools/augment_search.py --count 10 --seed 7 \
        --out reports/augment-search.json

Per family the report picks the augmentation with the most exact matches
(ties -> identity, the floor). Every augmentation ships here, measured —
the ones that add nothing stay in the table, zeroed out but present.
Deterministic, stdlib + Pillow only, offline.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402
import generator as G  # noqa: E402


def _thr176(img: Image.Image) -> Image.Image:
    return img.convert("L").point(lambda p: 255 if p >= 176 else 0).convert("RGB")


def _thr140(img: Image.Image) -> Image.Image:
    return img.convert("L").point(lambda p: 255 if p >= 140 else 0).convert("RGB")


AUGS = [
    ("identity", lambda im: im),
    ("autocontrast", lambda im: ImageOps.autocontrast(im.convert("RGB"))),
    ("equalize", lambda im: ImageOps.equalize(im.convert("L")).convert("RGB")),
    ("sharpen", lambda im: im.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))),
    ("median3", lambda im: im.filter(ImageFilter.MedianFilter(3))),
    ("thr176", _thr176),
    ("thr140", _thr140),
    ("invert", lambda im: ImageOps.invert(im.convert("RGB"))),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--families", default="")
    ap.add_argument("--eval-seed", type=int, default=0,
                    help="held-out seed: the per-family augmentation is FROZEN "
                         "from the selection seed and only then scored here "
                         "(select on 7, eval on 3; kills winner's curse)")
    ap.add_argument("--out", help="json report path")
    args = ap.parse_args()

    fams = [f for f in args.families.split(",") if f] or list(G.FAMILIES)
    per_family: list[dict] = []
    t0 = time.time()
    for fam in fams:
        # generate ONCE per family so every augmentation sees identical images
        items = [G.generate_one(fam, seed=args.seed, index=i) for i in range(args.count)]
        rows = {}
        for name, aug in AUGS:
            exact = 0
            msd = []
            for img, label in items:
                st = time.time()
                text = B.read_text(aug(img))[0]
                msd.append(time.time() - st)
                exact += text == label
            rows[name] = {"exact": round(exact / args.count, 4),
                          "median_s": round(sorted(msd)[len(msd) // 2], 3)}
        win = max(rows, key=lambda c: (rows[c]["exact"], c == "identity"))
        per_family.append({"family": fam, "winner": win, "augmentations": rows})

    gain = base = n_exact = 0
    for row in per_family:
        base += row["augmentations"]["identity"]["exact"] * args.count
        n_exact += row["augmentations"][row["winner"]]["exact"] * args.count
    total_items = args.count * len(fams)
    report = {
        "seed": args.seed, "count": args.count,
        "augmentations": [n for n, _ in AUGS],
        "floor_exact": round(base / total_items, 4),
        "best_augmented_exact": round(n_exact / total_items, 4),
        "gain_points": round((n_exact - base) / total_items * 100, 1),
        "per_family": per_family,
        "seconds": round(time.time() - t0, 1),
    }

    if args.eval_seed:
        aug_of = {n: a for n, a in AUGS}
        held = []
        fr_sum = id_sum = 0.0
        for row in per_family:
            fam, aug_name = row["family"], row["winner"]
            items = [G.generate_one(fam, seed=args.eval_seed, index=i)
                     for i in range(args.count)]
            fr = sum(B.read_text(aug_of[aug_name](img))[0] == label
                     for img, label in items)
            idn = sum(B.read_text(img)[0] == label for img, label in items)
            held.append({"family": fam, "augmentation_used": aug_name,
                         "exact": round(fr / args.count, 4),
                         "identity_exact": round(idn / args.count, 4)})
            fr_sum += fr
            id_sum += idn
        report["held_out"] = {
            "eval_seed": args.eval_seed,
            "frozen_augmented_exact": round(fr_sum / total_items, 4),
            "floor_exact_eval": round(id_sum / total_items, 4),
            "gain_points_eval": round((fr_sum - id_sum) / total_items * 100, 1),
            "per_family": held,
        }
        report["seconds"] = round(time.time() - t0, 1)

    print(f"augment search — {args.count} image(s)/family, seed {args.seed}, "
          f"{len(AUGS)} augmentations, {report['seconds']}s")
    print(f"  floor exact {report['floor_exact']*100:.1f}% -> "
          f"best-augmented {report['best_augmented_exact']*100:.1f}% "
          f"(+{report['gain_points']} points)")
    if "held_out" in report:
        h = report["held_out"]
        print(f"  HELD-OUT seed {h['eval_seed']} (augmentations frozen from seed {args.seed}): "
              f"frozen {h['frozen_augmented_exact']*100:.1f}% vs floor "
              f"{h['floor_exact_eval']*100:.1f}% -> {h['gain_points_eval']:+.1f} points")
    print("  per family (selection seed):")
    for row in per_family:
        cells = " ".join(f"{n}={row['augmentations'][n]['exact']*100:.0f}" for n, _ in AUGS)
        print(f"    {row['family']:<14} {cells}  -> {row['winner']}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")


if __name__ == "__main__":
    main()
