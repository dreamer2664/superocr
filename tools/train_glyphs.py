#!/usr/bin/env python3
"""train_glyphs.py — generate the glyph dataset and train the classifier.

Data is GENERATED, never committed (JOBS.md). The crops are produced through
the same path the segmenter uses (binarise -> tight crop -> 24x24), so the
classifier sees the same kind of image at train and at read time.

    python3 tools/train_glyphs.py                     # ~1 min, writes models/glyphcnn.npz
    python3 tools/train_glyphs.py --per-class 20 --epochs 3   # quick smoke
    python3 tools/train_glyphs.py --out /tmp/mine.npz --seed 7

Deterministic: same seed + same fonts + same library versions -> same weights
(the recipe records the seed and the measured accuracy).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))

from glyphcnn import CHARS, GlyphCNN, char_to_index, write_recipe  # noqa: E402
from segmentation import analyse, ink_mask, normalise_glyph  # noqa: E402
import reader as R  # noqa: E402  (classic matcher, used only for the agreement gate)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONTS = [
    "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSerif.ttf",
    "DejaVuSerif-Bold.ttf", "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf",
    "DejaVuSansMono-Oblique.ttf", "DejaVuSansMono-BoldOblique.ttf",
]


def available_fonts() -> list[str]:
    return [os.path.join(FONT_DIR, f) for f in FONTS
            if os.path.exists(os.path.join(FONT_DIR, f))]


def file_fingerprint(path) -> str | None:
    """sha256[:12] of a source file, or None if it is not there.

    The training data depends on generator.py and the segmenter, both of
    which move; without this, "same seed -> same weights" silently breaks
    when either lands (S10 finding, 12 Oct)."""
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else None


def data_fingerprint(x, y) -> str:
    """sha256[:16] of the exact dataset arrays (order-sensitive)."""
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(x).view(np.uint8))
    h.update(np.ascontiguousarray(y).view(np.uint8))
    return h.hexdigest()[:16]


def render_crop(ch: str, rng: np.random.Generator, fonts: list[str],
                size_px: int = 24) -> np.ndarray:
    """One augmented glyph crop, normalised exactly like the reader does."""
    size = int(rng.integers(18, 47))
    canvas = int(size * 2.2)
    img = Image.new("L", (canvas, canvas), 245)
    draw = ImageDraw.Draw(img)
    if fonts:
        font = ImageFont.truetype(fonts[int(rng.integers(0, len(fonts)))], size)
    else:                                    # no fonts installed: still trainable
        font = ImageFont.load_default(size=size)
    jitter = max(2, canvas // 10)
    draw.text((canvas // 2 + int(rng.integers(-jitter, jitter + 1)),
               canvas // 2 + int(rng.integers(-jitter, jitter + 1))),
              ch, fill=int(rng.integers(0, 40)), font=font, anchor="mm")
    if rng.random() < 0.7:                   # slight rotation
        img = img.rotate(float(rng.uniform(-6, 6)), resample=Image.BILINEAR,
                         fillcolor=245)
    if rng.random() < 0.4:                   # soft blur - gentle on purpose:
        img = img.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.2, 0.55))))
    # stroke-weight morphing is 15% only: Min/MaxFilter erases exactly the
    # stroke-width cues that separate I/l, O/o and X/x, and the first model
    # plateaued at 87% with case-pair confusions dominating (measured).
    if rng.random() < 0.15:
        img = img.filter(ImageFilter.MinFilter(3) if rng.random() < 0.5
                         else ImageFilter.MaxFilter(3))
    arr = np.asarray(img, dtype=np.float64)
    if rng.random() < 0.5:                   # sensor-ish noise
        arr = arr + rng.normal(0.0, float(rng.uniform(1.0, 6.0)), arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L")
    mask = ink_mask(img.convert("RGB"))
    ys, xs = np.nonzero(mask)
    if len(xs) < 4:                          # nothing survived: blank crop
        return np.zeros((size_px, size_px), dtype=np.float32)
    box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return normalise_glyph(mask, box, out_h=size_px, out_w=size_px)


def build_dataset(per_class: int, seed: int, size_px: int = 24, verbose=True):
    rng = np.random.default_rng(seed)
    fonts = available_fonts()
    if verbose:
        print(f"fonts: {len(fonts) or 'none - PIL default'} | chars: {len(CHARS)} "
              f"| per class: {per_class}")
    x = np.zeros((len(CHARS) * per_class, 1, size_px, size_px), dtype=np.float32)
    y = np.zeros(len(CHARS) * per_class, dtype=np.int64)
    i = 0
    t0 = time.time()
    for ci, ch in enumerate(CHARS):
        for _ in range(per_class):
            x[i, 0] = render_crop(ch, rng, fonts, size_px)
            y[i] = ci
            i += 1
    if verbose:
        print(f"rendered {i} crops in {time.time() - t0:.1f}s")
    return x, y


def stratified_split(x, y, val_every: int = 7):
    """Every val_every-th sample per class goes to validation."""
    val_idx = []
    for ci in range(len(CHARS)):
        idx = np.nonzero(y == ci)[0]
        val_idx.extend(idx[val_every - 1::val_every] if len(idx) >= val_every else [])
    val_idx = np.array(sorted(val_idx), dtype=int)
    train_mask = np.ones(len(y), dtype=bool)
    train_mask[val_idx] = False
    return x[train_mask], y[train_mask], x[val_idx], y[val_idx]


# ---------------------------------------------------------------------------
# generator.py as the training source (JOBS.md: "trained only on data from
# generator.py"). The generator is read from the repo root when present; when
# it is not (e.g. before its PR merges), the caller falls back to the synthetic
# renderer above and the recipe records which source was used.
# ---------------------------------------------------------------------------

def load_generator():
    path = ROOT / "generator.py"
    if not path.exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("superocr_generator", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def crops_from_generator(gen, sheets: int, seed: int, size_px: int, verbose=True,
                         min_agree: float = 0.85):
    """Render labelled sheets with generator.py and harvest glyph crops.

    A sheet is kept only when the segmenter's box count matches the label's
    glyph count exactly (spaces excluded) AND the classic matcher agrees with
    the label on >= min_agree of the boxes - a self-consistency filter, not a
    guess: mis-segmented sheets are dropped, never relabelled. The crops come
    out of the same analyse() the reader uses at inference time, so train and
    test see the same rendering, distortions and normalisation.

    The agreement gate (S10, 12 Oct) is sheet HYGIENE, not a score fix.
    Box-count alone did admit misaligned sheets (a fragment labelled with a
    full glyph); 30 such crops were measured in the harvested val block, all
    read wrong by one net and right by the older one. But the control run
    trained on synthetic crops ONLY - never seeing any harvest - reads the
    harvested val block at 82.9%, the same 82.9% as the harvest-trained run,
    so the junk did not measurably depress generalisation: ~83-84% is what
    harvested crops from this pipeline honestly hold. A model reading that
    block at 96%+ was trained on the same harvest generation as the block
    (overlap), not better - never compare harvested-val accuracies across
    models trained on different harvest generations. Keep the gate for sheet
    quality; do not claim a val gain from it (the gated run, 0.9200 on the
    own-split val, did not beat the synthetic-only control, 0.9251).
    """
    fonts = available_fonts()
    rng = np.random.default_rng(seed)
    families = list(gen.FAMILIES)
    x, y = [], []
    kept_sheets = skipped = 0
    t0 = time.time()
    for i in range(sheets):
        fam = families[int(rng.integers(0, len(families)))]
        img, label = gen.FAMILIES[fam](
            __import__("random").Random(int(rng.integers(1, 2**31))),
            int(rng.choice([gen.DEFAULT_SIZE[0], gen.DEFAULT_SIZE[0] * 2])),
            gen.DEFAULT_SIZE[1])
        label_chars = [c for c in label if c != " "]
        if not label_chars or any(c not in CHARS for c in label_chars):
            skipped += 1
            continue
        mask, boxes = analyse(img.convert("RGB"))
        if len(boxes) != len(label_chars):
            skipped += 1
            continue
        # agreement gate: the classic matcher must agree with the label on
        # most boxes, or the sheet's pieces are probably misaligned
        agree = 0
        for (box, _), ch in zip(boxes, label_chars):
            try:
                sub = mask[box[1]:box[3] + 1, box[0]:box[2] + 1]
                g = R.trim(sub)
                pred, _s = R.match_glyph(g) if g.any() else ("", 0.0)
                agree += int(pred == ch)
            except Exception:
                pass
        if agree < min_agree * len(label_chars):
            skipped += 1
            continue
        for (box, _), ch in zip(boxes, label_chars):
            x.append(normalise_glyph(mask, box, out_h=size_px, out_w=size_px))
            y.append(char_to_index(ch))
        kept_sheets += 1
        if verbose and i and i % 50 == 0:
            print(f"  sheet {i}/{sheets}: {len(x)} crops, {skipped} sheets skipped")
    if verbose:
        print(f"generator source: kept {kept_sheets}/{sheets} sheets, "
              f"{skipped} skipped, {len(x)} crops in {time.time() - t0:.1f}s")
    xa = np.zeros((len(x), 1, size_px, size_px), dtype=np.float32)
    for i, c in enumerate(x):
        xa[i, 0] = c
    return xa, np.array(y, dtype=np.int64)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--per-class", type=int, default=72)
    p.add_argument("--epochs", type=int, default=9)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--width", default="8,16", help="conv channel widths, e.g. 16,32")
    p.add_argument("--size", type=int, default=24, help="glyph crop size in pixels")
    p.add_argument("--dense", type=int, default=96)
    p.add_argument("--out", default=str(ROOT / "models" / "glyphcnn.npz"))
    p.add_argument("--data", default=str(ROOT / "data" / "glyphs.npz"),
                   help="where to cache the generated dataset (gitignored)")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--generator-sheets", type=int, default=0,
                   help="also harvest crops from generator.py sheets (preferred "
                        "source when generator.py exists); 0 = synthetic only")
    p.add_argument("--min-agree", type=float, default=0.85,
                   help="sheet is kept only if the classic matcher agrees with "
                        "the label on this fraction of its boxes (junk-crop gate)")
    p.add_argument("--synthetic-only", action="store_true",
                   help="skip generator.py harvesting entirely (control runs)")
    args = p.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.data).parent.mkdir(parents=True, exist_ok=True)

    cache_ok = (not args.no_cache and os.path.exists(args.data))
    if cache_ok:
        with np.load(args.data) as d:
            x, y = d["x"], d["y"]
        print(f"loaded cached dataset {args.data}: {len(y)} crops")
    else:
        xs, ys = build_dataset(args.per_class, args.seed, args.size)
        source = "synthetic"
        gensheets = args.generator_sheets if args.generator_sheets > 0 else 240
        gen = None if args.synthetic_only else load_generator()
        if gen is not None:
            xg, yg = crops_from_generator(gen, gensheets, args.seed + 1, args.size,
                                          min_agree=args.min_agree)
            if len(yg):
                xs = np.concatenate([xs, xg]); ys = np.concatenate([ys, yg])
                source = f"synthetic + {gensheets} generator.py sheets"
        elif args.generator_sheets:
            print("note: generator.py not in the repo yet - synthetic source only")
        x, y = xs, ys
        if not args.no_cache:
            np.savez_compressed(args.data, x=x, y=y)
            print(f"cached dataset -> {args.data} (gitignored)")
        globals()["_source"] = source

    xtr, ytr, xva, yva = stratified_split(x, y)
    print(f"train {len(ytr)} / val {len(yva)}")

    width = tuple(int(x) for x in args.width.split(","))
    net = GlyphCNN(seed=args.seed, width=width, dense=args.dense,
                   input_hw=(args.size, args.size))
    t0 = time.time()
    history = net.fit(xtr, ytr, xva, yva, epochs=args.epochs, verbose=True)
    seconds = time.time() - t0
    val_acc = history[-1][2] or 0.0

    net.save(args.out)
    size = os.path.getsize(args.out)
    recipe = {
        "model": "glyphcnn",
        "architecture": f"conv3x3({width[0]})-pool-conv3x3({width[1]})-pool-fc{args.dense}-fc62",
        "classes": len(CHARS), "input": f"{args.size}x{args.size} ink-bright crop",
        "trained_on": (f"{globals().get('_source', 'synthetic')} crops via "
                       f"tools/train_glyphs.py (numpy/PIL only; crops through the "
                       f"same segmenter the reader uses)"),
        "seed": args.seed, "per_class": len(y) // len(CHARS),
        "data_sha256": data_fingerprint(x, y),
        "source_files": {
            "generator.py": file_fingerprint(ROOT / "generator.py"),
            "readers/segmentation.py": file_fingerprint(ROOT / "readers" / "segmentation.py"),
            "tools/train_glyphs.py": file_fingerprint(ROOT / "tools" / "train_glyphs.py"),
        },
        "train_samples": int(len(ytr)), "val_samples": int(len(yva)),
        "epochs": args.epochs, "final_val_acc": round(float(val_acc), 4),
        "train_seconds": round(seconds, 1), "weights_bytes": size,
        "weights": os.path.relpath(args.out, ROOT),
        "history": [{"epoch": e, "loss": round(l, 4), "val_acc": (round(v, 4) if v is not None else None)}
                    for e, l, v in history],
    }
    rpath = write_recipe(args.out, recipe)
    print(f"val acc {val_acc:.4f} | data {recipe['data_sha256']} | {size} bytes "
          f"-> {args.out} | recipe {rpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
