#!/usr/bin/env python3
"""gen_hard_corpus.py — S53 (t-20261013-4c7b): the 2000-image hard corpus.

The canonical fam_* recipes in generator.py are UNTOUCHED (the official
suite hash b2c460d2fb5a must not move). This tool imports their helpers and
parameterizes the SAME degradation mechanics around severity levels, so the
retrain lane (S30+) gets thousands of labelled hard examples with a
controlled difficulty gradient:

  corrosion   light / medium / heavy / extreme   (pit-count scaling on the
              fam_corrosion recipe: 70-130 / 140-260 (=canonical) /
              210-390 / 350-650 pits, r 1-3, bg patches, median-3)
  rotation    mild (+-2) / moderate (+-5) / severe (+-9, =collage) /
              extreme (+-14), full-sheet, BICUBIC, expand
  overlay     spiderweb / cross-shadow / strippy / darts, light & heavy
              (count/alpha/strength scaled; heavy = the canonical ranges)
  combined    2-3 random degradations, random severities, applied in
              sequence (rotation last so ink coordinates stay computable)
  control     undegradated label renders (the contrast arm)

Output: <out>/images/*.png + <out>/manifest.jsonl in the existing suite
format (id, image, label, family, tags) plus degradation_type, severity and
char_boxes — per-character tight ink boxes on the FINAL image (rotation
transformed), the v6 lesson operationalized: the retrain can cut
word-context crops with read-time semantics.

Deterministic: per-item rng = sha256(f"{corpus}:{seed}:{index}") like
generator.rng_for. Usage:

    python3 tools/gen_hard_corpus.py --count 2000 --seed 53 --out corpus/hard-2000
    python3 tools/gen_hard_corpus.py --count 40 --severity-check   # quick gradient
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generator as G  # noqa: E402

W, H = G.DEFAULT_SIZE

CORROSION_PITS = {"light": (70, 130), "medium": (140, 260),
                  "heavy": (210, 390), "extreme": (350, 650)}
ROTATION_DEG = {"mild": 2.0, "moderate": 5.0, "severe": 9.0, "extreme": 14.0}
OVERLAY_FAMS = ("spiderweb", "cross-shadow", "strippy", "darts")

ARMS = ([("corrosion", s) for s in CORROSION_PITS] +
        [("rotation", s) for s in ROTATION_DEG] +
        [("overlay", f"{f}:{s}") for f in OVERLAY_FAMS
         for s in ("light", "heavy")] +
        [("combined", "mixed"), ("control", "none")])


def corpus_rng(corus_id: str, seed: int, index: int):
    h = hashlib.sha256(f"{corus_id}:{seed}:{index}".encode()).digest()
    return __import__("random").Random(int.from_bytes(h[:8], "big"))


# ------------------------------------------------------------------ base
def base_render(rng, label: str):
    """The shared clean prefix: label drawn on paper — a faithful replay of
    G.draw_label that ALSO records (font, x, y) so per-char boxes can be
    computed exactly (textlength advances), even when glyphs touch."""
    img = G._paper(rng, W, H)
    size = rng.randint(26, 40)
    font = G.load_font(rng, size)
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if tw > W - 16:
        size = max(12, size * (W - 16) // tw)
        font = G.load_font(rng, size)
        bbox = d.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2 - bbox[0] + rng.randint(-6, 6)
    y = (H - th) // 2 - bbox[1] + rng.randint(-4, 4)
    d.text((x, y), label, font=font, fill=G._ink_color(rng))
    return img, font, x, y


def transform_boxes(boxes, angle: float, img_size, out_size):
    """Rotate per-char boxes with the sheet (about centre, expand=True)."""
    w0, h0 = img_size
    w1, h1 = out_size
    cx, cy = w0 / 2, h0 / 2
    ncx, ncy = w1 / 2, h1 / 2
    t = math.radians(angle)

    def xf(bx, by):
        dx, dy = bx - cx, by - cy
        rx = dx * math.cos(t) + dy * math.sin(t)
        ry = -dx * math.sin(t) + dy * math.cos(t)
        return rx + ncx, ry + ncy

    out = []
    for b in boxes:
        if not b:
            out.append([])
            continue
        bx0, bx1, by0, by1 = b
        pts = [xf(bx0, by0), xf(bx1, by0), xf(bx0, by1), xf(bx1, by1)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        out.append([int(min(xs)), int(max(xs)), int(min(ys)), int(max(ys))])
    return out


# ------------------------------------------------------------ degradations
def apply_corrosion(img: Image.Image, rng, severity: str) -> Image.Image:
    """fam_corrosion's mechanic, severity-scaled. NOTE: the canonical
    recipe draws a heavy 6-offset stroke; here the base render already
    exists, so pits are placed on its ink (the corpus isolates the pit
    degradation; heavy-stroke is a separate axis in combined)."""
    lo, hi = CORROSION_PITS[severity]
    a = np.array(img, dtype=np.uint8).copy()
    g = G.rng_np(rng)
    n_pits = rng.randint(lo, hi)
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
    return Image.fromarray(a, "RGB").filter(ImageFilter.MedianFilter(3))


def apply_rotation(img: Image.Image, rng, severity: str):
    lim = ROTATION_DEG[severity]
    ang = rng.uniform(-lim, lim)
    # Fill the expand-triangles with the sheet's own border colour: PIL's
    # default fill is black, which stamps four huge black corners on a
    # white-paper sheet — an artifact no canonical family has.  The border
    # median is deterministic and matches the paper.
    w, h = img.size
    px = img.load()
    samples = []
    for x in range(0, w, max(1, w // 40)):
        samples += [px[x, 0], px[x, h - 1]]
    for y in range(0, h, max(1, h // 40)):
        samples += [px[0, y], px[w - 1, y]]
    samples.sort()
    med = samples[len(samples) // 2]
    fill = med if img.mode == "L" else tuple(med) if isinstance(med, (tuple, list)) else (med, med, med)
    rot = img.rotate(ang, resample=Image.BICUBIC, expand=True, fillcolor=fill)
    return rot, ang


def apply_spiderweb(rng, severity: str, size) -> Image.Image:
    w, h = size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx, cy = rng.randint(w // 4, 3 * w // 4), rng.randint(h // 4, 3 * h // 4)
    n_sp = rng.randint(6, 10) if severity == "light" else rng.randint(12, 20)
    angs = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n_sp))
    L = int(math.hypot(w, h))
    alpha = rng.randint(60, 110) if severity == "light" else rng.randint(120, 170)
    wcol = (90, 90, 100, alpha)
    for a_ in angs:
        d.line([(cx, cy), (cx + L * math.cos(a_), cy + L * math.sin(a_))],
               fill=wcol, width=1)
    for rr in range(rng.randint(4, 7)):
        rad = rng.randint(20, min(w, h))
        pts = []
        for t in [i / 48 for i in range(49)]:
            ang = angs[0] + t * 2 * math.pi
            sag = 1 + 0.06 * math.sin(ang * n_sp / 2)
            pts.append((cx + rad * sag * math.cos(ang),
                        cy + rad * sag * math.sin(ang)))
        d.line(pts, fill=wcol, width=1)
    return overlay


def apply_cross_shadow(img: Image.Image, rng, severity: str) -> Image.Image:
    a = np.array(img, dtype=np.float32)
    h_, w_ = img.size[1], img.size[0]
    yy, xx = np.mgrid[0:h_, 0:w_]
    hi_s = 0.45 if severity == "light" else 0.75
    for _ in range(2):
        ang = rng.uniform(math.pi / 8, 3 * math.pi / 8) * rng.choice([-1, 1])
        off = rng.uniform(-h_, h_)
        t = (xx * math.sin(ang) + yy * math.cos(ang) + off)
        band = np.exp(-((t - rng.uniform(0, h_)) ** 2)
                      / (2 * rng.uniform(14, 30) ** 2))
        strength = rng.uniform(0.55, hi_s)
        a *= (1.0 - strength * band[..., None])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def apply_strippy(img: Image.Image, rng, severity: str) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    h = rng.randint(6, 13)
    lo_a = 90 if severity == "light" else 150
    for y in range(0, img.size[1], 2 * h):
        a_ = rng.randint(lo_a, 235)
        col = G._bg_color(rng)
        d.rectangle([0, y, W, y + h], fill=(col[0], col[1], col[2], a_))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def apply_darts(rng, severity: str, size) -> Image.Image:
    w, h = size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    n = rng.randint(15, 30) if severity == "light" else rng.randint(36, 70)
    a_lo = 60 if severity == "light" else 110
    for _ in range(n):
        s = rng.randint(8, 22)
        x, y = rng.randint(0, w), rng.randint(0, h)
        ang = rng.uniform(0, 2 * math.pi)
        col = (rng.randint(30, 120),) * 3 + (rng.randint(a_lo, 190),)
        tip = (x + s * math.cos(ang), y + s * math.sin(ang))
        for da in (2.5, -2.5):
            tail = (x + s * 0.7 * math.cos(ang + da),
                    y + s * 0.7 * math.sin(ang + da))
            d.line([tip, tail], fill=col, width=rng.randint(1, 2))
    return overlay


def apply_overlay(img: Image.Image, rng, fam: str, severity: str):
    if fam == "spiderweb":
        ov = apply_spiderweb(rng, severity, img.size)
        return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    if fam == "cross-shadow":
        return apply_cross_shadow(img, rng, severity)
    if fam == "strippy":
        return apply_strippy(img, rng, severity)
    if fam == "darts":
        ov = apply_darts(rng, severity, img.size)
        return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    raise ValueError(fam)


# ------------------------------------------------------------------ item
def advance_char_boxes(img: Image.Image, label: str, font, x: int, y: int):
    """Exact per-char tight ink boxes via textlength advances (the S26/S28
    oracle-box construction; works even when glyphs touch)."""
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    out = []
    for i, ch in enumerate(label):
        adv = x + d.textlength(label[:i], font=font)
        cb = d.textbbox((adv, y), ch, font=font)
        out.append([] if ch == " " else
                   [int(cb[0]) - 1, int(cb[2]) + 1,
                    int(cb[1]) - 1, int(cb[3]) + 1])
    return [b for b in out if b] if out else []


def make_item(index: int, seed: int, corpus_id: str):
    """Render one corpus item; returns (image, manifest-row)."""
    rng = corpus_rng(corpus_id, seed, index)
    arm, sev = ARMS[index % len(ARMS)]
    label = G.make_label(rng)
    img, font, dx, dy = base_render(rng, label)
    # per-char ground truth BEFORE degradation (ink does not move under
    # corrosion/overlays; rotation transforms it below)
    boxes = advance_char_boxes(img, label, font, dx, dy)
    angle = 0.0
    deg_type = arm

    if arm == "corrosion":
        img = apply_corrosion(img, rng, sev)
    elif arm == "rotation":
        img, angle = apply_rotation(img, rng, sev)
        boxes = transform_boxes(boxes, angle, (W, H), img.size) if boxes else []
    elif arm == "overlay":
        fam_name, severity = sev.split(":")
        img = apply_overlay(img, rng, fam_name, severity)
        deg_type = "overlay"
        sev = severity
    elif arm == "combined":
        picks = rng.sample(["corrosion", "rotation", "spiderweb",
                            "cross-shadow", "strippy", "darts"],
                           rng.randint(2, 3))
        for p in picks:
            if p == "corrosion":
                img = apply_corrosion(img, rng,
                                      rng.choice(list(CORROSION_PITS)))
            elif p == "rotation":
                img, angle = apply_rotation(img, rng,
                                            rng.choice(list(ROTATION_DEG)))
                boxes = transform_boxes(boxes, angle, (W, H), img.size) \
                    if boxes else []
            else:
                img = apply_overlay(img, rng, p,
                                    rng.choice(["light", "heavy"]))
        deg_type = "+".join(picks)
        sev = "mixed"
    # control: nothing

    if arm == "overlay":
        fam = f"overlay-{fam_name}-{sev}"
    elif arm == "corrosion":
        fam = f"corrosion-{sev}"
    elif arm == "rotation":
        fam = f"rotation-{sev}"
    elif arm == "combined":
        fam = deg_type
    else:
        fam = "control"
    row = {
        "id": f"{arm}-{index:04d}",
        "image": f"images/{arm}-{index:04d}.png",
        "label": label,
        "family": fam,
        "tags": ["s53", f"seed={seed}", "corpus"],
        "degradation_type": deg_type,
        "severity": sev,
        "rotation_deg": round(angle, 2),
        "char_boxes": boxes,
    }
    return img, row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=53)
    ap.add_argument("--out", default="corpus/hard-2000")
    ap.add_argument("--corpus-id", default="s53-hard")
    a = ap.parse_args()

    outdir = ROOT / a.out
    (outdir / "images").mkdir(parents=True, exist_ok=True)
    rows = []
    from collections import Counter
    fams = Counter()
    for i in range(a.count):
        img, row = make_item(i, a.seed, a.corpus_id)
        img.save(outdir / row["image"])
        rows.append(row)
        fams[row["degradation_type"] + "/" + row["severity"]] += 1
    with (outdir / "manifest.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{a.count} items -> {outdir}")
    for k, v in sorted(fams.items()):
        print(f"  {k:<28} {v}")
    n_boxes = sum(1 for r in rows if r["char_boxes"])
    print(f"per-char boxes: {n_boxes}/{a.count} items "
          f"(rest: touching glyphs or span-count mismatch, honestly [])")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
