#!/usr/bin/env python3
"""gen_real_corpus.py — S42 (t-20261013-44ba): realistic-degradation corpus.

S29/S30 showed the synthetic degradation models don't match the real
failure modes: S43's census says 63/77 hard misses are SEGMENTATION
failures, and the S30 retrain hit its wall at stroke destruction, not at
scale windows (S35, NO-GO). So "realistic" here means degradation that
PRODUCES those failure modes, not cosmetic damage:

  texcorrosion  texture-aware corrosion: pits placed by a value-noise
                field (clustered "rough zones") + edge-biased stroke
                erosion (thinning/breaking) — identity destruction
  paperdegrade  soft stains, yellowing gradient, fiber lines, crease —
                multimodal histograms that attack thresholding (OTSU)
  perspective   4-corner homography warps (trapezoid/skew, not uniform
                rotation) — projection-profile and deskew failures
  inkbleed      variable-radius dilation + soft blur re-composite, plus
                deliberate inter-glyph bridges — the touching-glyph
                split_wide/segmentation failures that own the residue
  control       undegradated renders

Builds on the S53 generator (gen_hard_corpus): same deterministic per-item
sha-rng, same advance-based char_boxes (perspective-transformed exactly
through the homography), same manifest schema. Output is JPEG q90 — a
TRAINING corpus (gitignored, regenerable); canonical PNG eval suites are
untouched.

    python3 tools/gen_real_corpus.py --count 10000 --seed 42 \
        --out corpus/real10k
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import generator as G  # noqa: E402
from gen_hard_corpus import (advance_char_boxes, base_render,  # noqa: E402
                             corpus_rng)

W, H = G.DEFAULT_SIZE
CORPUS_ID = "s42-real"

TEX = {  # (pit_lo, pit_hi, edge_erode_p, ink_floor)
    "light": (120, 240, 0.05, 0.75),
    "moderate": (220, 380, 0.12, 0.55),
    "heavy": (300, 500, 0.18, 0.35),
}
PAPER = {  # (n_stains, yellow_w, n_fibers, n_creases)
    "light": (2, 0.18, 30, 0),
    "moderate": (4, 0.30, 50, 1),
    "heavy": (7, 0.45, 80, 2),
}
PERSP = {"light": 6, "moderate": 14, "heavy": 26}   # corner jitter, px
BLEED = {  # (dilate_r, blur_sigma, touch_p)
    "light": (1, 0.8, 0.15),
    "moderate": (2, 1.4, 0.40),
    "heavy": (3, 2.2, 0.70),
}
SEVS = ("light", "moderate", "heavy")


# ------------------------------------------------------------------ helpers
def noise_field(rng, w, h, gx=6, gy=3) -> np.ndarray:
    """Smooth value-noise field in [0,1] — the 'texture' pits cluster on."""
    grid = np.array([[rng.random() for _ in range(gx)] for _ in range(gy)],
                    dtype=np.float32)
    im = Image.fromarray((grid * 255).astype(np.uint8), "L")
    return np.asarray(im.resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0


def apply_texcorrosion(img: Image.Image, rng, sev: str) -> Image.Image:
    a = np.array(img, dtype=np.float32).copy()
    field = noise_field(rng, W, H)
    ink0 = a.mean(axis=2) < 120
    ink_budget = ink0.sum()
    ys, xs = np.where(ink0)
    lo, hi, erode_p, floor = TEX[sev]
    if len(xs):
        n = rng.randint(lo, hi)
        tries = 0
        placed = 0
        removed_ink = 0
        floor_n = ink_budget * floor
        while placed < n and tries < n * 8:
            if ink_budget - removed_ink < floor_n:
                break  # damage budget: stop before stroke annihilation
            tries += 1
            i = rng.randrange(len(xs))
            px, py = int(xs[i]), int(ys[i])
            if rng.random() > 0.25 + 0.75 * field[py, px]:
                continue  # texture-gated: pits cluster on rough zones
            r = rng.randint(1, 3)
            y0, y1 = max(0, py - r), min(H, py + r)
            x0, x1 = max(0, px - r), min(W, px + r)
            yy, xx = np.ogrid[y0:y1, x0:x1]
            m = (xx - px) ** 2 + (yy - py) ** 2 <= r * r
            patch = np.array(G._bg_color(rng), dtype=np.float32)
            region_ink = (a[y0:y1, x0:x1].mean(axis=2) < 120) & m
            removed_ink += int(region_ink.sum())
            a[y0:y1, x0:x1][m] = patch
            placed += 1
    # edge-biased stroke erosion: thin/break strokes along their edges
    ink = a.mean(axis=2) < 120
    shifts = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    edge = np.zeros_like(ink)
    for dy, dx in shifts:
        shifted = np.roll(ink, (dy, dx), axis=(0, 1))
        edge |= ink & ~shifted
    ys, xs = np.where(edge)
    remaining = int(ink.sum())
    floor_n = ink_budget * floor
    for i in range(len(xs)):
        if remaining <= floor_n:
            break
        if rng.random() < erode_p:
            a[ys[i], xs[i]] = np.array(G._bg_color(rng), dtype=np.float32)
            remaining -= 1
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def apply_paperdegrade(img: Image.Image, rng, sev: str) -> Image.Image:
    a = np.array(img, dtype=np.float32).copy()
    n_stains, yellow_w, n_fibers, n_creases = PAPER[sev]
    # yellowing gradient (diagonal ramp)
    ramp = np.linspace(0.0, 1.0, W)[None, :, None] * \
        np.linspace(0.2, 1.0, H)[:, None, None]
    yellow = np.array([214, 196, 158], dtype=np.float32)
    a = a * (1 - yellow_w * ramp) + yellow * (yellow_w * ramp)
    # soft radial stains
    yy, xx = np.mgrid[0:H, 0:W]
    for _ in range(n_stains):
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(25, 80)
        col = np.array([rng.randint(140, 185), rng.randint(125, 165),
                        rng.randint(100, 135)], dtype=np.float32)
        a_col = np.array([rng.randint(150, 190), rng.randint(140, 175),
                          rng.randint(115, 150)], dtype=np.float32)
        strength = rng.uniform(0.25, 0.55)
        m = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (r / 2) ** 2)))
        a = a * (1 - strength * m[..., None]) + a_col * (strength * m[..., None])
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    # fiber lines
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for _ in range(n_fibers):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        ang = rng.uniform(0, math.pi)
        L = rng.uniform(8, 30)
        dark = rng.random() < 0.5
        col = (120, 112, 96, rng.randint(12, 35)) if dark else (255, 250, 235, rng.randint(12, 30))
        d.line([(x, y), (x + L * math.cos(ang), y + L * math.sin(ang))],
               fill=col, width=1)
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    # creases: dark line with an adjacent highlight
    for _ in range(n_creases):
        ang = rng.uniform(-0.6, 0.6)
        x0 = rng.uniform(0, W)
        dx, dy = math.cos(ang) * W, math.sin(ang) * H
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        d.line([(x0, -4), (x0 + dx, H + 4)], fill=(70, 62, 50, rng.randint(50, 80)), width=2)
        d.line([(x0 + 3, -4), (x0 + dx + 3, H + 4)], fill=(255, 252, 240, rng.randint(40, 70)), width=1)
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    return img.filter(ImageFilter.GaussianBlur(0.6))


def _homography(src_quad, dst_quad):
    """Solve the 8 coeffs mapping src -> dst (PIL PERSPECTIVE wants
    coeffs for (x,y) -> (X,Y) = ((ax+by+c)/(gx+hy+1), (dx+ey+f)/(gx+hy+1))."""
    A, B = [], []
    for (x, y), (X, Y) in zip(src_quad, dst_quad):
        A.append([x, y, 1, 0, 0, 0, -x * X, -y * X]); B.append(X)
        A.append([0, 0, 0, x, y, 1, -x * Y, -y * Y]); B.append(Y)
    return np.linalg.solve(np.array(A, dtype=np.float64),
                           np.array(B, dtype=np.float64))


def apply_perspective(img: Image.Image, rng, sev: str, boxes):
    jit = PERSP[sev]
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    dst = [(x + rng.uniform(-jit, jit), y + rng.uniform(-jit, jit))
           for x, y in src]
    # c maps INPUT coords -> OUTPUT coords (used for the truth boxes);
    # PIL's PERSPECTIVE transform needs the INVERSE (it samples, for each
    # output pixel, the input at coeffs(p)) — get it by swapping the quads.
    c = _homography(src, dst)
    c_img = _homography(dst, src)
    paper = img.getpixel((rng.randint(0, W - 1), rng.randint(0, 3)))
    out = img.transform((W, H), Image.PERSPECTIVE,
                        tuple(c_img.tolist()), Image.BICUBIC,
                        fillcolor=paper)

    def xf(bx, by):
        g = c[6] * bx + c[7] * by + 1.0
        return ((c[0] * bx + c[1] * by + c[2]) / g,
                (c[3] * bx + c[4] * by + c[5]) / g)

    tboxes = []
    for b in boxes:
        pts = [xf(b[0], b[2]), xf(b[1], b[2]), xf(b[0], b[3]), xf(b[1], b[3])]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        tboxes.append([int(min(xs)), int(max(xs)), int(min(ys)), int(max(ys))])
    return out, tboxes


def apply_inkbleed(img: Image.Image, rng, sev: str, boxes, label) -> Image.Image:
    r, sigma, touch_p = BLEED[sev]
    a = np.array(img, dtype=np.float32)
    ink = a.mean(axis=2) < 120
    ink_col = tuple(int(v) for v in a.reshape(-1, 3)[ink.reshape(-1)].mean(axis=0)) \
        if ink.any() else (30, 30, 30)
    # inter-glyph bridges: deliberate touching (the seg killer)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    nb = [b for b in boxes if b]
    for b1, b2 in zip(nb, nb[1:]):
        gap = b2[0] - b1[1]
        if 0 < gap <= 5 and rng.random() < touch_p:
            y0 = max(b1[2], b2[2]) + 1
            y1 = min(b1[3], b2[3]) - 1
            if y1 > y0:
                yb = rng.randint(y0, y1)
                d.line([(b1[1] - 1, yb), (b2[0] + 1, yb)],
                       fill=ink_col + (255,), width=rng.randint(1, 2))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    # soft bleed: dilate + blur the ink, re-composite dark
    a = np.array(img, dtype=np.float32)
    ink = a.mean(axis=2) < 120
    inkL = Image.fromarray((ink * 255).astype(np.uint8), "L")
    inkL = inkL.filter(ImageFilter.MaxFilter(2 * r + 1))
    inkL = inkL.filter(ImageFilter.GaussianBlur(sigma))
    soft = np.asarray(inkL, dtype=np.float32) / 255.0
    target = np.array(ink_col, dtype=np.float32)
    a = a * (1 - soft[..., None] * 0.85) + target * (soft[..., None] * 0.85)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


# ------------------------------------------------------------------ item
FAM_SEV_COUNTS = ([("texcorrosion", s, 800) for s in SEVS] +
                  [("paperdegrade", s, 800) for s in SEVS] +
                  [("perspective", s, 800) for s in SEVS] +
                  [("inkbleed", s, 800) for s in SEVS] +
                  [("control", "none", 400)])


def build_arm_list(seed: int):
    arms = [[f, s] for f, s, n in FAM_SEV_COUNTS for _ in range(n)]
    random.Random(seed).shuffle(arms)  # deterministic stratified interleave
    return arms


def make_item(index: int, seed: int, arms):
    rng = corpus_rng(CORPUS_ID, seed, index)
    arm, sev = arms[index]
    label = G.make_label(rng)
    img, font, dx, dy = base_render(rng, label)
    boxes = advance_char_boxes(img, label, font, dx, dy)

    if arm == "texcorrosion":
        img = apply_texcorrosion(img, rng, sev)
    elif arm == "paperdegrade":
        img = apply_paperdegrade(img, rng, sev)
    elif arm == "perspective":
        img, boxes = apply_perspective(img, rng, sev, boxes)
    elif arm == "inkbleed":
        img = apply_inkbleed(img, rng, sev, boxes, label)
    # control: nothing

    return img, {
        "id": f"{arm}-{index:04d}",
        "image": f"images/{arm}-{index:04d}.jpg",
        "label": label,
        "family": f"{arm}-{sev}",
        "tags": ["s42", f"seed={seed}", "corpus", "realism"],
        "degradation_type": arm,
        "severity": sev,
        "rotation_deg": 0.0,
        "char_boxes": boxes,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="corpus/real10k")
    ap.add_argument("--jpeg-q", type=int, default=90)
    args = ap.parse_args()

    arms = build_arm_list(args.seed)[: args.count]
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    manifest = open(out / "manifest.jsonl", "w")
    n_boxes = 0
    for i in range(len(arms)):
        img, row = make_item(i, args.seed, arms)
        img.save(out / row["image"], "JPEG", quality=args.jpeg_q, optimize=True)
        manifest.write(json.dumps(row) + "\n")
        n_boxes += len(row["char_boxes"])
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(arms)}", flush=True)
    manifest.close()
    h = hashlib.sha256(open(out / "manifest.jsonl", "rb").read()).hexdigest()
    from collections import Counter
    fams = Counter(r["family"] for r in
                   (json.loads(l) for l in open(out / "manifest.jsonl")))
    print(f"done: {len(arms)} items, char boxes {n_boxes}, "
          f"manifest sha256 {h[:16]}")
    for f, n in sorted(fams.items()):
        print(f"  {f:28s} {n}")


if __name__ == "__main__":
    main()
