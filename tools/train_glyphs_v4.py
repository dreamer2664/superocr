#!/usr/bin/env python3
"""train_glyphs_v4.py — v3's trainer with the degradations that kill v3
(S28: corroded letters 0.25-0.37, rotated crops 0.25-0.27) in the training
mix. Same net, same protocol, same seed discipline as v3
(tools/train_glyphs.py, per_class 311 / epochs 34 / seed 11) — the ONLY
differences are in the crop renderer:

  - heavy stroke: 6-offset draw (fam_corrosion's recipe) at p=0.35
  - corrosion pits: bg-coloured disks ON ink pixels, radius 1-3, density
    ~1 pit / 150 ink px (fam_corrosion's 140-260 pits per full line scaled
    to crop ink area) + MedianFilter(3), at p=0.85 given heavy
  - rotation widened ±6 -> ±9 deg (fam_collage) at p=0.7

Everything else (fonts, sizes, blur/morph/noise rates, 24x24 normalisation
through the reader's own ink_mask/normalise_glyph, split, GlyphCNN.fit,
recipe) is imported from train_glyphs.py unchanged.

    python3 tools/train_glyphs_v4.py                # v3 protocol -> models/glyphcnn-v4.npz
    python3 tools/train_glyphs_v4.py --per-class 40 --epochs 3   # smoke
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))
sys.path.insert(0, str(ROOT / "tools"))

from train_glyphs import (available_fonts, data_fingerprint,  # noqa: E402
                           stratified_split, load_generator,
                           crops_from_generator)
from glyphcnn import CHARS, GlyphCNN, char_to_index, write_recipe  # noqa: E402
from segmentation import ink_mask, normalise_glyph  # noqa: E402

V4_AUG = {"p_heavy": 0.35, "p_pits_given_heavy": 0.85,
          "rot_deg": 9.0, "pit_density": 150}


def render_crop_v4(ch: str, rng: np.random.Generator, fonts: list[str],
                   size_px: int = 24) -> np.ndarray:
    """v3's render_crop with the S28-named degradations added."""
    size = int(rng.integers(18, 47))
    canvas = int(size * 2.2)
    img = Image.new("L", (canvas, canvas), 245)
    draw = ImageDraw.Draw(img)
    if fonts:
        font = ImageFont.truetype(fonts[int(rng.integers(0, len(fonts)))], size)
    else:
        font = ImageFont.load_default(size=size)
    jitter = max(2, canvas // 10)
    cx = canvas // 2 + int(rng.integers(-jitter, jitter + 1))
    cy = canvas // 2 + int(rng.integers(-jitter, jitter + 1))
    ink = int(rng.integers(0, 40))
    heavy = rng.random() < V4_AUG["p_heavy"]
    if heavy:  # fam_corrosion's 6-offset heavy stroke
        for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1)):
            draw.text((cx + ox, cy + oy), ch, fill=ink, font=font, anchor="mm")
    else:
        draw.text((cx, cy), ch, fill=ink, font=font, anchor="mm")
    if rng.random() < 0.7:  # rotation, widened to +-9 (fam_collage)
        img = img.rotate(float(rng.uniform(-V4_AUG["rot_deg"],
                                           V4_AUG["rot_deg"])),
                         resample=Image.BILINEAR, fillcolor=245)
    pits = heavy and rng.random() < V4_AUG["p_pits_given_heavy"]
    if pits:  # corrosion pits: bg disks on ink, then median-3
        arr = np.array(img)
        dark = arr < 120
        ys, xs = np.nonzero(dark)
        n_pits = max(1, len(xs) // V4_AUG["pit_density"])
        for _ in range(n_pits):
            i = int(rng.integers(0, len(xs)))
            px, py = int(xs[i]), int(ys[i])
            r = int(rng.integers(1, 4))
            y0, y1 = max(0, py - r), min(arr.shape[0], py + r)
            x0, x1 = max(0, px - r), min(arr.shape[1], px + r)
            yy, xx = np.ogrid[y0:y1, x0:x1]
            m = (xx - px) ** 2 + (yy - py) ** 2 <= r * r
            arr[y0:y1, x0:x1][m] = 245
        img = Image.fromarray(arr).filter(ImageFilter.MedianFilter(3))
    if rng.random() < 0.4:
        img = img.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.2, 0.55))))
    if rng.random() < 0.15:
        img = img.filter(ImageFilter.MinFilter(3) if rng.random() < 0.5
                         else ImageFilter.MaxFilter(3))
    arr = np.asarray(img, dtype=np.float64)
    if rng.random() < 0.5:
        arr = arr + rng.normal(0.0, float(rng.uniform(1.0, 6.0)), arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L")
    mask = ink_mask(img.convert("RGB"))
    ys, xs = np.nonzero(mask)
    if len(xs) < 4:
        return np.zeros((size_px, size_px), dtype=np.float32)
    box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return normalise_glyph(mask, box, out_h=size_px, out_w=size_px)


def build_dataset_v4(per_class: int, seed: int, size_px: int = 24):
    rng = np.random.default_rng(seed)
    fonts = available_fonts()
    print(f"fonts: {len(fonts) or 'none'} | chars: {len(CHARS)} | "
          f"per class: {per_class} | aug: {V4_AUG}")
    x = np.zeros((len(CHARS) * per_class, 1, size_px, size_px), dtype=np.float32)
    y = np.zeros(len(CHARS) * per_class, dtype=np.int64)
    i = 0
    t0 = time.time()
    for ci, ch in enumerate(CHARS):
        for _ in range(per_class):
            x[i, 0] = render_crop_v4(ch, rng, fonts, size_px)
            y[i] = ci
            i += 1
    print(f"rendered {i} crops in {time.time() - t0:.1f}s")
    return x, y


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--per-class", type=int, default=311)
    p.add_argument("--epochs", type=int, default=34)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--width", default="8,16")
    p.add_argument("--size", type=int, default=24)
    p.add_argument("--dense", type=int, default=96)
    p.add_argument("--out", default=str(ROOT / "models" / "glyphcnn-v4.npz"))
    p.add_argument("--generator-sheets", type=int, default=240)
    args = p.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    xs, ys = build_dataset_v4(args.per_class, args.seed, args.size)
    source = "synthetic-v4 (corrosion+rotation augmented)"
    gen = load_generator()
    if gen is not None and args.generator_sheets:
        xg, yg = crops_from_generator(gen, args.generator_sheets,
                                       args.seed + 1, args.size)
        if len(yg):
            xs = np.concatenate([xs, xg])
            ys = np.concatenate([ys, yg])
            source += f" + {args.generator_sheets} generator.py sheets"
    x, y = xs, ys
    xtr, ytr, xva, yva = stratified_split(x, y)
    print(f"train {len(ytr)} / val {len(yva)}")

    width = tuple(int(v) for v in args.width.split(","))
    net = GlyphCNN(seed=args.seed, width=width, dense=args.dense,
                   input_hw=(args.size, args.size))
    t0 = time.time()
    history = net.fit(xtr, ytr, xva, yva, epochs=args.epochs, verbose=True)
    seconds = time.time() - t0
    val_acc = history[-1][2] or 0.0
    net.save(args.out)

    recipe = {
        "model": "glyphcnn",
        "architecture": f"conv3x3({width[0]})-pool-conv3x3({width[1]})-"
                        f"pool-fc{args.dense}-fc62",
        "classes": len(CHARS), "input": f"{args.size}x{args.size} ink-bright crop",
        "trained_on": f"{source} crops via tools/train_glyphs_v4.py "
                      f"(aug: {V4_AUG})",
        "seed": args.seed, "per_class": args.per_class,
        "data_sha256": data_fingerprint(x, y),
        "epochs": args.epochs, "final_val_acc": round(val_acc, 4),
        "history": [{"epoch": e, "loss": round(l, 4), "val_acc": round(v, 4)}
                    for e, l, v in history],
        "train_samples": len(ytr), "val_samples": len(yva),
        "train_seconds": round(seconds, 1),
        "weights": args.out, "weights_bytes": os.path.getsize(args.out),
        "baseline": "v3 (models/glyphcnn-v3.npz, val 0.9394) — v4 differs "
                    "ONLY in crop-render augmentation",
    }
    rp = ROOT / "recipes" / "glyphcnn-v4.json"
    write_recipe(args.out, recipe)
    print(f"saved {args.out} ({recipe['weights_bytes']} bytes) "
          f"val_acc={val_acc:.4f} recipe -> {rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
