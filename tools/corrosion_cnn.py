#!/usr/bin/env python3
"""tools/corrosion_cnn.py — corrosion is a representation wall; learn
through it (t-20261011-be57).

Microscopic diagnosis (see reports/corrosion-diagnosis.md): corrosion
mangles strokes so far that the true char is not even top-5 in template
scoring ('o' -> 'l' @ 0.954). Template scoring cannot fix that; the
committed CNN can — IF it sees corroded glyph crops in training. But
reports/s6-summary.md phase 3 self-training drew labels from the net's
own confident predictions; here the SEGMENTATION is trustworthy
(1.02/true) so we harvest exactly-aligned (glyph, true-char) pairs from
the generator's training labels instead — no pseudo-anything.

  collect  corrosion images (seed 71), keep images where piece count ==
           true glyph count, align pieces to label chars in order
  train    fine-tune the committed glyphcnn on those crops
  evaluate corrosion + easy control through the floor's own segmentation
           with the CNN as the classifier, on held-out seed 7, and print
           base-vs-tuned. Weights are saved only with --save.

    python3 tools/corrosion_cnn.py --train-n 30 --eval-count 10 \
        --out reports/corrosion-cnn.json
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
from readers.glyphcnn import GlyphCNN, char_to_index, index_to_char  # noqa: E402
from readers.segmentation import normalise_glyph  # noqa: E402


def floor_pieces(img: Image.Image) -> tuple[np.ndarray, list[np.ndarray], list[list[int]]]:
    """The floor pipeline up to per-word piece lists. Returns (mask, pieces,
    word_of_piece) so the reader can re-insert spaces exactly like the floor does."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.trim(R.despeck(R.otsu(a)))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    pieces: list[np.ndarray] = []
    word_of: list[int] = []
    wi = 0
    for word in R.segment(mask):
        word_pieces = []
        for x0, x1 in word:
            for g in R.split_wide(R.trim(mask[:, x0:x1])):
                if g.shape[0] >= 6 and g.sum() >= 10:
                    word_pieces.append(g)
        if word_pieces:
            pieces.extend(word_pieces)
            word_of.extend([wi] * len(word_pieces))
            wi += 1
    return mask, pieces, word_of


def crop_of(piece: np.ndarray) -> np.ndarray:
    h, w = piece.shape
    return normalise_glyph(piece, (0, 0, w - 1, h - 1))[None, :, :]


def collect(family: str, n: int, seed: int) -> tuple[np.ndarray, np.ndarray, dict]:
    xs, ys = [], []
    used = seen = 0
    for i in range(n):
        img, label = G.generate_one(family, seed=seed, index=i)
        seen += 1
        true = [c for c in label if c != " "]
        _, pieces, _ = floor_pieces(img)
        if len(pieces) != len(true):
            continue
        used += 1
        for j, p in enumerate(pieces):
            xs.append(crop_of(p)[0])
            ys.append(char_to_index(true[j]))
    stats = {"images_seen": seen, "images_aligned": used, "glyphs": len(xs)}
    return np.array(xs, dtype=np.float32)[:, None, :, :], np.array(ys, dtype=np.int64), stats


def read_with_net(img: Image.Image, net: GlyphCNN) -> str:
    _, pieces, word_of = floor_pieces(img)
    if not pieces:
        return ""
    crops = np.stack([crop_of(p)[0] for p in pieces])
    probs = net.forward(crops[:, None, :, :].astype(net.p["w1"].dtype))[0]
    out: list[str] = []
    last_w = word_of[0]
    for j in range(len(pieces)):
        if word_of[j] != last_w:
            out.append(" ")
            last_w = word_of[j]
        out.append(index_to_char(int(probs[j].argmax())))
    return "".join(out)


def _char_acc(label: str, text: str) -> float:
    l1, l2 = label.replace(" ", ""), text.replace(" ", "")
    tot = max(len(l1), len(l2)) or 1
    return sum(a == b for a, b in zip(l1, l2)) / tot


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-n", type=int, default=30)
    ap.add_argument("--seed-train", type=int, default=71)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--eval-count", type=int, default=10)
    ap.add_argument("--seed-eval", type=int, default=7)
    ap.add_argument("--families", default="corrosion,easy")
    ap.add_argument("--out", help="json report path")
    ap.add_argument("--save", help="write fine-tuned weights here")
    args = ap.parse_args()

    base = GlyphCNN.load(str(ROOT / "models" / "glyphcnn.npz"))
    t0 = time.time()
    x, y, stats = collect("corrosion", args.train_n, args.seed_train)
    collect_s = round(time.time() - t0, 1)
    print(f"collected {stats['glyphs']} aligned corrosion glyphs from "
          f"{stats['images_aligned']}/{stats['images_seen']} images | {collect_s}s")
    if not len(x):
        print("nothing aligned — corrosion set empty, abort (report writes 0)")
        return

    tuned = GlyphCNN(init_from={k: v.copy() for k, v in base.p.items()})
    t0 = time.time()
    hist = tuned.fit(x, y, epochs=args.epochs, lr=args.lr, lr_end=args.lr / 5,
                     batch=64, seed=3, verbose=True)
    fit_s = round(time.time() - t0, 1)
    print(f"fine-tune: {args.epochs} epochs | loss {hist[0][1]:.4f} -> {hist[-1][1]:.4f} | {fit_s}s")

    fams = [f for f in args.families.split(",") if f]
    rows = {}
    t0 = time.time()
    for fam in fams:
        for name, net in (("base", base), ("tuned", tuned)):
            exact = cok = 0.0
            for i in range(args.eval_count):
                img, label = G.generate_one(fam, seed=args.seed_eval, index=i)
                text = read_with_net(img, net)
                exact += text == label
                cok += _char_acc(label, text)
            rows.setdefault(fam, {})[name] = {"exact": round(exact / args.eval_count, 2),
                                              "char": round(cok / args.eval_count, 3)}
    eval_s = round(time.time() - t0, 1)
    report = {"train": {"family": "corrosion", "n": args.train_n, "seed": args.seed_train,
                        "epochs": args.epochs, "lr": args.lr, **stats,
                        "loss_first": round(hist[0][1], 4), "loss_last": round(hist[-1][1], 4)},
              "eval": {"seed": args.seed_eval, "count": args.eval_count, "families": rows},
              "seconds": {"collect": collect_s, "fit": fit_s, "eval": eval_s}}
    print(f"held-out (seed {args.seed_eval}, {args.eval_count}/family):")
    for fam in fams:
        r = rows[fam]
        d = (r["tuned"]["exact"] - r["base"]["exact"]) * 100
        print(f"  {fam:<10} base {r['base']['exact']*100:4.0f}%/{r['base']['char']*100:.0f}c "
              f"-> tuned {r['tuned']['exact']*100:4.0f}%/{r['tuned']['char']*100:.0f}c ({d:+.0f})")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")
    if args.save:
        tuned.save(args.save)
        print(f"fine-tuned weights -> {args.save}")


if __name__ == "__main__":
    main()
