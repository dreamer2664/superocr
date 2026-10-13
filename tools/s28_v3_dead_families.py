#!/usr/bin/env python3
"""s28_v3_dead_families.py — v3 letter identity on the two families the
classic pipeline cannot read even with truth masks (S27: corrosion/collage
0/16). The image-side lane go/no-go (t-20261013-d3c3).

S26 closed DIGIT identity under corrosion-grade noise (34.7% vs 87.7%
control). LETTER identity on the same recipe — and on collage's rotated
cards — was unmeasured. This probe measures both:

  arm corrosion-{corroded,control}
      s26's renderer verbatim (heavy 6-offset stroke, pits, median-3, oracle
      per-char tight ink boxes), fed the 8 real corrosion-miss LABELS from
      the seed-1 suite; letters scored.

  arm collage-{asis,derotated}
      fam_collage-style word cards (white card, text at 24-34px, rotate
      ±9 deg BICUBIC). Oracle per-char boxes recorded on the UNROTATED card.
      as-is      : crop cut from the rotated image at the transformed box
                   (what a pipeline without de-rotation would extract)
      derotated  : crop cut from the unrotated card (perfect de-rotation
                   ceiling; the angle is known at replay time)

Pieces are cropped from the reader's own front-end mask (autocontrast ->
otsu fallback -> despeck), scored by PieceCNN(glyphcnn-v3).opinions.
Minimum-size skips counted honestly. Receipts:
reports/s28-v3-dead-families/probe-v1.{json,txt}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))

import baseline as B  # noqa: E402
import generator as G  # noqa: E402
import reader as R  # noqa: E402
from piece_cnn import PieceCNN  # noqa: E402

W, H = 640, 180


def render_corrosion(seed: int, text: str, pits: bool):
    """s26 renderer, unchanged (see tools/s26_digit_corrosion_probe.py)."""
    import random
    rng = random.Random(seed)
    base = G._paper(rng, W, H)
    size = rng.randint(26, 40)
    font = G.load_font(rng, size)
    d = ImageDraw.Draw(base)
    bb = d.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if tw > W - 16:
        size = max(12, size * (W - 16) // tw)
        font = G.load_font(rng, size)
        bb = d.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (W - tw) // 2 - bb[0]
    y = (H - th) // 2 - bb[1]
    ink = G._ink_color(rng)
    for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1)):
        d.text((x + ox, y + oy), text, font=font, fill=ink)
    boxes = []
    for i, ch in enumerate(text):
        adv = x + d.textlength(text[:i], font=font)
        cb = d.textbbox((adv, y), ch, font=font)
        boxes.append((int(cb[0]) - 1, int(cb[2]) + 1, int(cb[1]) - 1,
                      int(cb[3]) + 1))
    a = np.array(base, dtype=np.uint8).copy()
    if pits:
        g = G.rng_np(rng)
        n_pits = rng.randint(140, 260)
        dark = a.mean(axis=2) < 120
        ys, xs = np.where(dark)
        if len(xs):
            for _ in range(n_pits):
                i = int(g.integers(0, len(xs)))
                px, py = int(xs[i]), int(ys[i])
                r = int(g.integers(1, 4))
                y0, y1 = max(0, py - r), min(H, py + r)
                x0, x1 = max(0, px - r), min(W, px + r)
                yy, xx = np.ogrid[y0:y1, x0:x1]
                m = (xx - px) ** 2 + (yy - py) ** 2 <= r * r
                patch = np.array(G._bg_color(rng), dtype=np.uint8)
                a[y0:y1, x0:x1][m] = patch
    img = Image.fromarray(a, "RGB").filter(ImageFilter.MedianFilter(3))
    fname = getattr(font, "path", "default").split("/")[-1]
    return img, boxes, fname


def render_collage_card(seed: int, word: str):
    """A fam_collage-style card: text on a white card, rotated ±9 deg.
    Returns (rotated RGB image, unrotated mask image, per-char boxes on the
    UNROTATED card, rotation angle, font name)."""
    import math
    import random
    rng = random.Random(seed)
    font_size = rng.randint(24, 34)
    font = G.load_font(rng, font_size)
    tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    bb = tmp.textbbox((0, 0), word, font=font)
    twd, th = bb[2] - bb[0], bb[3] - bb[1]
    card = Image.new("L", (twd + 12, th + 10), 255)
    d = ImageDraw.Draw(card)
    x0, y0 = 6 - bb[0], 5 - bb[1]
    d.text((x0, y0), word, font=font, fill=0)
    boxes = []
    for i, ch in enumerate(word):
        adv = x0 + d.textlength(word[:i], font=font)
        cb = d.textbbox((adv, y0), ch, font=font)
        boxes.append((int(cb[0]) - 1, int(cb[2]) + 1, int(cb[1]) - 1,
                      int(cb[3]) + 1))
    ang = rng.uniform(-9, 9)
    rot = card.rotate(ang, resample=Image.BICUBIC, expand=True)
    # white canvas: the card (235-250) blends toward it and the only DARK
    # pixels are the text, so the reader's otsu extracts the glyphs.
    # (A 225-gray canvas made the mask pick up the CARD as ink — inverted
    # card fragments — and every collage-asis number measured on it was
    # garbage; caught during S29's v4 comparison.)
    canvas = Image.new("L", (W, H), 255)
    px = (W - rot.width) // 2
    py = (H - rot.height) // 2
    canvas.paste(rot, (px, py))
    rot_rgb = Image.merge("RGB", (canvas, canvas, canvas))
    # transform box corners through the same rotation (about card centre,
    # expand=True shifts by the new half-size), then translate by (px, py)
    cx, cy = card.width / 2, card.height / 2
    ncx, ncy = rot.width / 2, rot.height / 2
    t = math.radians(ang)

    def xf(bx, by):
        dx, dy = bx - cx, by - cy
        rx = dx * math.cos(t) + dy * math.sin(t)
        ry = -dx * math.sin(t) + dy * math.cos(t)
        return rx + ncx + px, ry + ncy + py

    rboxes = []
    for (bx0, bx1, by0, by1) in boxes:
        pts = [xf(bx0, by0), xf(bx1, by0), xf(bx0, by1), xf(bx1, by1)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        rboxes.append((int(min(xs)) - 1, int(max(xs)) + 1,
                       int(min(ys)) - 1, int(max(ys)) + 1))
    fname = getattr(font, "path", "default").split("/")[-1]
    return rot_rgb, card, boxes, rboxes, ang, fname


def mask_for(img: Image.Image) -> np.ndarray:
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = B._family_mask(img, a, None)
    if mask is None:
        lv = B._otsu_level(a)
        mask = a < (lv * 0.85 if 128 <= lv <= 150 else lv)
        if mask.mean() > 0.5:
            mask = ~mask
    return R.trim(R.despeck(mask))


def trim_offset(img: Image.Image):
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    full = B._family_mask(img, a, None)
    if full is None:
        lv = B._otsu_level(a)
        full = a < (lv * 0.85 if 128 <= lv <= 150 else lv)
        if full.mean() > 0.5:
            full = ~full
    full = R.despeck(full)
    rows = np.where(full.any(axis=1))[0]
    cols = np.where(full.any(axis=0))[0]
    return (int(rows[0]), int(cols[0])) if len(rows) and len(cols) else (0, 0)


def crop_mask(mask: np.ndarray, box) -> np.ndarray:
    x0, x1, y0, y1 = box
    h, w = mask.shape
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    c = mask[y0:y1, x0:x1]
    return c if c.any() else None


def score_arm(net: PieceCNN, pieces, chars):
    """pieces: list[(crop, true_char)]; returns stats dict."""
    n = correct = skipped = 0
    probs_ok, probs_bad = [], []
    conf = Counter()
    by_font = {}
    for crop, ch, fname in pieces:
        if crop is None or crop.shape[0] < 4 or crop.shape[1] < 2:
            skipped += 1
            continue
        pred, p = net.opinions([crop])[0]
        n += 1
        ok = pred == ch
        correct += ok
        (probs_ok if ok else probs_bad).append(p)
        if not ok:
            conf[f"{ch}->{pred}"] += 1
        bf = by_font.setdefault(fname, [0, 0])
        bf[0] += ok
        bf[1] += 1
    return {
        "n": n, "correct": correct, "skipped": skipped,
        "acc": round(correct / n, 4) if n else None,
        "p_ok_mean": round(float(np.mean(probs_ok)), 3) if probs_ok else None,
        "p_bad_mean": round(float(np.mean(probs_bad)), 3) if probs_bad else None,
        "p_bad_ge_90": int(sum(p >= 0.9 for p in probs_bad)),
        "top_confusions": conf.most_common(8),
        "by_font": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_font.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/hard/manifest.jsonl")
    ap.add_argument("--out", default="reports/s28-v3-dead-families")
    ap.add_argument("--seed", type=int, default=71000)
    ap.add_argument("--weights", default=None,
                    help="PieceCNN weights (default: the repo default)")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(ROOT / a.manifest)]
    corr = [r for r in rows if r["family"] == "corrosion"]
    coll = [r for r in rows if r["family"] == "collage"]
    net = PieceCNN(a.weights)
    t0 = time.time()
    arms = {}

    # --- corrosion arms (s26 renderer, real miss labels, letters scored) ---
    for arm, pits in (("corrosion-corroded", True), ("corrosion-control", False)):
        pieces = []
        for si, r in enumerate(corr):
            text = r["label"]
            img, boxes, fname = render_corrosion(a.seed + si, text, pits)
            mask = mask_for(img)
            dy, dx = trim_offset(img)
            for (bx0, bx1, by0, by1), ch in zip(boxes, text):
                if ch == " ":
                    continue
                crop = crop_mask(mask, (bx0 - dx, bx1 - dx, by0 - dy, by1 - dy))
                pieces.append((crop, ch, fname))
        arms[arm] = score_arm(net, pieces, None)

    # --- collage arms (rotated as-is vs perfect de-rotation) ---
    for arm, mode in (("collage-asis", "rot"), ("collage-derotated", "flat")):
        pieces = []
        for si, r in enumerate(coll):
            words = r["label"].split()
            for wi, word in enumerate(words):
                seed = a.seed + 1000 + si * 10 + wi
                rot_rgb, card, boxes, rboxes, ang, fname = \
                    render_collage_card(seed, word)
                if mode == "rot":
                    img = rot_rgb
                    boxes_use = rboxes
                else:
                    img = Image.merge(
                        "RGB", (card, card, card))
                    boxes_use = boxes
                mask = mask_for(img)
                dy, dx = trim_offset(img)
                for (bx0, bx1, by0, by1), ch in zip(boxes_use, word):
                    crop = crop_mask(mask, (bx0 - dx, bx1 - dx,
                                            by0 - dy, by1 - dy))
                    pieces.append((crop, ch, fname))
        arms[arm] = score_arm(net, pieces, None)

    dt = time.time() - t0
    out = {"seed": a.seed, "labels": {"corrosion": len(corr),
                                      "collage": len(coll)},
           "weights": a.weights or "repo-default", "seconds": round(dt, 1),
           "arms": arms}
    outdir = ROOT / a.out
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "probe-v1.json").write_text(json.dumps(out, indent=2))
    lines = [f"S28 — v3 letter identity on the dead families "
             f"(seed {a.seed}, {len(corr)} corrosion + {len(coll)} collage "
             f"real miss labels, letters scored, {dt:.0f}s)"]
    for arm, s in arms.items():
        lines.append(f"\n{arm:<20} n={s['n']:<4} acc={s['acc']} "
                     f"skip={s['skipped']} p_ok={s['p_ok_mean']} "
                     f"p_bad={s['p_bad_mean']} bad>=.9:{s['p_bad_ge_90']}")
        lines.append(f"  top confusions: {s['top_confusions'][:6]}")
        lines.append(f"  by font: {s['by_font']}")
    (outdir / "probe-v1.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
