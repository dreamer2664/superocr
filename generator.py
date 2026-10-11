#!/usr/bin/env python3
"""superocr generator — the hard families (t-20261011-e071).

Each hard family from JOBS.md is one seeded function:

    image, label = FAMILY[name](rng, W, H)

* the label is the EXACT text in the image, case-sensitive, and the only
  ground truth the bench scores against;
* every function is deterministic: same seed -> byte-identical PNG
  (given the same fonts/FreeType, see README);
* only stdlib + numpy + Pillow, CPU, no downloads.

The bench (t-2f3d) consumes the manifest written by `--out`:
one JSON object per line: {"file", "label", "family", "seed"}.

The EASY family (t-ec08) is a sibling task: add one function here, register
it in FAMILIES, and the CLI/tests pick it up unchanged.

Usage:
    python3 generator.py --list
    python3 generator.py --family snow --count 8 --seed 42 --out out/hard_snow
    python3 generator.py --family all  --count 2 --seed 7  --out out/hard_all
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import string
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# --------------------------------------------------------------------------
# fonts
# --------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf",
]


def available_fonts() -> list[str]:
    """DejaVu faces present on this machine (deterministic: fixed order)."""
    return [p for p in _FONT_CANDIDATES if Path(p).exists()]


def load_font(rng: random.Random, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A random available face at `size`; falls back to PIL's default face."""
    fonts = available_fonts()
    if fonts:
        return ImageFont.truetype(rng.choice(fonts), size)
    try:  # Pillow >= 9.2 can size the bundled face
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# --------------------------------------------------------------------------
# labels
# --------------------------------------------------------------------------

# neutral concrete nouns/verbs — no real brands, no look-alike traps by design
# (confusability is the READER's problem; the generator's job is honest labels)
_WORDS = [
    "amber", "anchor", "basil", "beacon", "birch", "bolt", "bramble", "brass",
    "breeze", "brook", "canyon", "carbon", "cedar", "chisel", "cinder", "cipher",
    "clover", "cobalt", "comet", "copper", "coral", "crane", "crest", "crystal",
    "delta", "drift", "dune", "ember", "falcon", "fathom", "feldspar", "fennel",
    "fjord", "flint", "forge", "fossil", "garnet", "glacier", "granite", "grove",
    "harbor", "hazel", "heather", "heron", "hollow", "horizon", "indigo", "island",
    "ivory", "jasper", "juniper", "keel", "kestrel", "lagoon", "lantern", "larch",
    "ledge", "linen", "lupine", "marble", "meadow", "meridian", "mesa", "meteor",
    "mistral", "moss", "nebula", "nectar", "nimbus", "north", "oasis", "obsidian",
    "orchid", "osprey", "otter", "parchment", "pebble", "penguin", "pinnacle",
    "plume", "prairie", "quartz", "quill", "raven", "reef", "ridge", "rivet",
    "rosette", "sable", "saffron", "sage", "sail", "salmon", "scarp", "sequoia",
    "shale", "signal", "slate", "sparrow", "spring", "stalactite", "summit",
    "sundial", "surf", "swift", "talon", "tarn", "thicket", "thistle", "tide",
    "timber", "topaz", "torque", "trail", "tundra", "umber", "valley", "vapor",
    "vellum", "vertex", "violet", "walrus", "wharf", "willow", "wren", "zenith",
    "zephyr", "zigzag",
]

_DIGIT_SHAPES = ["%d", "%02d", "%03d", "%d%d"]


def case_word(rng: random.Random, w: str) -> str:
    """Mixed-case patterns: lower / Title / UPPER / rAnDoM-ish (deterministic)."""
    r = rng.random()
    if r < 0.45:
        return w
    if r < 0.70:
        return w.capitalize()
    if r < 0.85:
        return w.upper()
    return "".join(c.upper() if rng.random() < 0.5 else c for c in w)


def make_label(rng: random.Random) -> str:
    """2..5 words, mixed case, digits in ~40% of labels, exact ground truth."""
    n = rng.randint(2, 5)
    words = [case_word(rng, rng.choice(_WORDS)) for _ in range(n)]
    if rng.random() < 0.4:
        shape = rng.choice(_DIGIT_SHAPES)
        digits = shape % tuple(rng.randint(0, 9) for _ in range(shape.count("%")))
        words.insert(rng.randint(1, len(words)), digits)
    return " ".join(words)


# --------------------------------------------------------------------------
# base render
# --------------------------------------------------------------------------

def _bg_color(rng: random.Random) -> tuple[int, int, int]:
    v = rng.randint(232, 250)
    tint = rng.randint(-6, 6)
    return (max(0, min(255, v + tint)), max(0, min(255, v)), max(225, min(255, v - tint)))


def _ink_color(rng: random.Random) -> tuple[int, int, int]:
    v = rng.randint(10, 48)
    return (v, v, v + rng.randint(0, 10))


def _paper(rng: random.Random, W: int, H: int) -> Image.Image:
    """Warm paper with fine grain (never flat — flat backgrounds are easy)."""
    base = np.zeros((H, W, 3), dtype=np.int16)
    c = np.array(_bg_color(rng), dtype=np.int16)
    base[:] = c
    grain = rng_np(rng).integers(-4, 5, size=(H, W, 1), dtype=np.int16)
    base += grain
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def rng_np(rng: random.Random) -> np.random.Generator:
    """A numpy generator seeded from the single python rng (one seed stream)."""
    return np.random.default_rng(rng.randint(0, 2**62))


def draw_label(img: Image.Image, rng: random.Random, label: str,
               font_size: tuple[int, int] = (26, 40),
               ink: tuple[int, int, int] | None = None) -> Image.Image:
    """Draw `label` centered on img, one line, random face/size. Returns img."""
    W, H = img.size
    size = rng.randint(*font_size)
    font = load_font(rng, size)
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if tw > W - 16:  # shrink to fit
        size = max(12, size * (W - 16) // tw)
        font = load_font(rng, size)
        bbox = d.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2 - bbox[0] + rng.randint(-6, 6)
    y = (H - th) // 2 - bbox[1] + rng.randint(-4, 4)
    d.text((x, y), label, font=font, fill=ink or _ink_color(rng))
    return img


def rng_for(family: str, seed: int, index: int) -> random.Random:
    """Deterministic per-sample stream independent of iteration order."""
    h = hashlib.sha256(f"{family}:{seed}:{index}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


# --------------------------------------------------------------------------
# the twelve hard families — one function each
# --------------------------------------------------------------------------

def fam_snow(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """TV-snow: dense white speckle + soft flakes over clean text."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    a = np.array(img, dtype=np.int16)
    g = rng_np(rng)
    mask = g.random((H, W, 1)) < 0.06
    a[np.repeat(mask, 3, axis=2)] += 140  # bright speckle
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(rng.randint(10, 18)):  # soft flakes
        r = rng.randint(5, 16)
        x, y = rng.randint(0, W), rng.randint(0, H)
        flake = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(flake).ellipse([x - r, y - r, x + r, y + r],
                                      fill=(255, 255, 255, rng.randint(60, 120)))
        img = Image.alpha_composite(img.convert("RGBA"), flake.filter(ImageFilter.GaussianBlur(2)))
    return img.convert("RGB"), label


def fam_spiderweb(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """A fine web (radial spokes + sagging rings) laid over the text."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx, cy = rng.randint(W // 4, 3 * W // 4), rng.randint(H // 4, 3 * H // 4)
    n_sp = rng.randint(12, 20)
    angs = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n_sp))
    L = int(math.hypot(W, H))
    wcol = (90, 90, 100, rng.randint(120, 170))
    for a in angs:
        d.line([(cx, cy), (cx + L * math.cos(a), cy + L * math.sin(a))], fill=wcol, width=1)
    for rr in range(rng.randint(4, 7)):  # sagging capture threads
        rad = rng.randint(20, min(W, H))
        pts = []
        for t in [i / 48 for i in range(49)]:
            ang = angs[0] + t * 2 * math.pi
            sag = 1 + 0.06 * math.sin(ang * n_sp / 2)
            pts.append((cx + rad * sag * math.cos(ang), cy + rad * sag * math.sin(ang)))
        d.line(pts, fill=wcol, width=1)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img, label


def fam_split(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Torn-scan: the sheet is split and the two halves slide vertically."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    cut = rng.randint(int(W * 0.35), int(W * 0.65))
    dy = rng.randint(10, 22) * rng.choice([-1, 1])
    left, right = img.crop((0, 0, cut, H)), img.crop((cut, 0, W, H))
    out = _paper(rng, W, H)
    out.paste(left, (0, 0))
    out.paste(right, (cut, dy))
    # expose a hairline of the other half's paper in the gap
    if dy > 0:
        out.paste(right.crop((0, 0, right.width, dy)), (cut, 0))
    else:
        out.paste(right.crop((0, H + dy, right.width, H)), (cut, H + dy))
    return out, label


def fam_stitch(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Panorama stitch: vertical strips re-placed with jitter and seam overlap."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    n = rng.randint(4, 6)
    edges = sorted([0, W] + [rng.randint(int(W * 0.1), int(W * 0.9)) for _ in range(n - 2)])
    out = _paper(rng, W, H)
    for i in range(len(edges) - 1):
        x0, x1 = edges[i], edges[i + 1]
        strip = img.crop((x0, 0, x1, H))
        dx, dyy = rng.randint(-7, 7), rng.randint(-9, 9)
        out.paste(strip, (x0 + dx, dyy))
        d = ImageDraw.Draw(out)
        d.line([(x0 + dx, 0), (x0 + dx, H)], fill=(170, 168, 164), width=1)  # seam
    return out, label


def fam_strippy(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Banding: opaque/semi-opaque horizontal stripes laid over the text."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    h = rng.randint(6, 13)
    for y in range(0, H, 2 * h):
        a = rng.randint(150, 235)
        col = _bg_color(rng)
        d.rectangle([0, y, W, y + h], fill=(col[0], col[1], col[2], a))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img, label


def fam_cut(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Scissor cuts: thin background-coloured slashes slice the glyphs."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    d = ImageDraw.Draw(img)
    paper = _bg_color(rng)
    n = rng.randint(2, 4)
    for k in range(n):
        # at least one slash goes through the ink band; the rest wander
        y = rng.randint(H // 2 - 16, H // 2 + 16) if k == 0 else rng.randint(H // 5, 4 * H // 5)
        ang = rng.uniform(-0.22, 0.22)  # mostly horizontal slashes
        x0, x1 = rng.randint(0, W // 4), rng.randint(3 * W // 4, W)
        dy = (x1 - x0) * math.tan(ang)
        w = rng.randint(3, 5)
        d.line([(x0, y), (x1, y + dy)], fill=paper, width=w)
    return img, label


def fam_collage(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Word scraps pasted on a busy patchwork, slightly rotated and offset."""
    label_words_rng = random.Random(rng.randint(0, 2**62))
    words = [case_word(label_words_rng, label_words_rng.choice(_WORDS))
             for _ in range(label_words_rng.randint(2, 4))]
    if label_words_rng.random() < 0.4:
        words.insert(label_words_rng.randint(1, len(words)), str(label_words_rng.randint(10, 99)))
    label = " ".join(words)
    out = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(out)
    patch = 28
    for y in range(0, H, patch):  # busy patchwork background
        for x in range(0, W, patch):
            v = rng.randint(150, 235)
            d.rectangle([x, y, x + patch, y + patch],
                        fill=(v + rng.randint(-9, 9), v, v - rng.randint(-9, 9)))
    d.rectangle([0, 0, W - 1, H - 1], outline=(120, 118, 112), width=2)
    font_size = rng.randint(24, 34)
    font = load_font(rng, font_size)
    tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    widths = []
    for wd in words:
        bb = tmp.textbbox((0, 0), wd, font=font)
        widths.append(bb[2] - bb[0])
    total = sum(widths) + 14 * (len(words) - 1)
    x = max(8, (W - total) // 2 + rng.randint(-8, 8))
    ink = _ink_color(rng)
    for wd, twd in zip(words, widths):
        bb = tmp.textbbox((0, 0), wd, font=font)
        th = bb[3] - bb[1]
        card = Image.new("RGB", (twd + 12, th + 10),
                         (rng.randint(235, 250), rng.randint(235, 250), rng.randint(230, 248)))
        ImageDraw.Draw(card).text((6 - bb[0], 5 - bb[1]), wd, font=font, fill=ink)
        card = card.rotate(rng.uniform(-9, 9), resample=Image.BICUBIC, expand=True)
        y = (H - card.height) // 2 + rng.randint(-14, 14)
        out.paste(card, (x, y))
        x += twd + 14 + rng.randint(-4, 6)
    return out, label


def fam_corrosion(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Rust-eaten glyphs: pits and holes chewed out of the strokes.

    The strokes are drawn heavy first so the pitting corrodes but does not
    erase: a careful reader must still be able to score 95/100 (the bar)."""
    label = make_label(rng)
    base = _paper(rng, W, H)
    size = rng.randint(26, 40)
    font = load_font(rng, size)
    d = ImageDraw.Draw(base)
    bb = d.textbbox((0, 0), label, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if tw > W - 16:
        size = max(12, size * (W - 16) // tw)
        font = load_font(rng, size)
        bb = d.textbbox((0, 0), label, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (W - tw) // 2 - bb[0]
    y = (H - th) // 2 - bb[1]
    ink = _ink_color(rng)
    for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1)):  # heavy stroke
        d.text((x + ox, y + oy), label, font=font, fill=ink)
    ink_img = base
    a = np.array(ink_img, dtype=np.uint8).copy()
    g = rng_np(rng)
    n_pits = rng.randint(140, 260)
    dark = a.mean(axis=2) < 120  # where the ink is
    ys, xs = np.where(dark)
    if len(xs):
        for _ in range(n_pits):
            i = int(g.integers(0, len(xs)))
            x, y = int(xs[i]), int(ys[i])
            r = int(g.integers(1, 4))
            y0, y1 = max(0, y - r), min(H, y + r)
            x0, x1 = max(0, x - r), min(W, x + r)
            yy, xx = np.ogrid[y0:y1, x0:x1]
            m = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
            patch = np.array(_bg_color(rng), dtype=np.uint8)
            a[y0:y1, x0:x1][m] = patch
    img = Image.fromarray(a, "RGB").filter(ImageFilter.MedianFilter(3))
    return img, label


def fam_cross_shadow(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Two dark shadow bands cross the sheet, collapsing local contrast."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    a = np.array(img, dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    for _ in range(2):
        ang = rng.uniform(math.pi / 8, 3 * math.pi / 8) * rng.choice([-1, 1])
        off = rng.uniform(-H, H)
        t = (xx * math.sin(ang) + yy * math.cos(ang) + off)
        band = np.exp(-((t - rng.uniform(0, H)) ** 2) / (2 * rng.uniform(14, 30) ** 2))
        strength = rng.uniform(0.55, 0.75)
        a *= (1.0 - strength * band[..., None])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB"), label


def fam_darts(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """A scatter of small dart/chevron marks over the page."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for _ in range(rng.randint(36, 70)):
        s = rng.randint(8, 22)
        x, y = rng.randint(0, W), rng.randint(0, H)
        ang = rng.uniform(0, 2 * math.pi)
        col = (rng.randint(30, 120),) * 3 + (rng.randint(110, 190),)
        tip = (x + s * math.cos(ang), y + s * math.sin(ang))
        for da in (2.5, -2.5):  # two tail strokes = a dart
            tail = (x + s * 0.7 * math.cos(ang + da), y + s * 0.7 * math.sin(ang + da))
            d.line([tip, tail], fill=col, width=rng.randint(1, 2))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img, label


def fam_obstruction(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Semi-transparent smudges and blobs lie over part of the text."""
    label = make_label(rng)
    img = draw_label(_paper(rng, W, H), rng, label)
    img = img.convert("RGBA")
    for _ in range(rng.randint(2, 4)):
        blob = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(blob)
        x, y = rng.randint(W // 8, 7 * W // 8), rng.randint(H // 8, 7 * H // 8)
        rx, ry = rng.randint(30, 90), rng.randint(18, 50)
        v = rng.randint(120, 235)
        alpha = rng.randint(85, 165)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(v, v, v, alpha))
        blob = blob.filter(ImageFilter.GaussianBlur(rng.uniform(2, 5)))
        img = Image.alpha_composite(img, blob)
    return img.convert("RGB"), label


def fam_dark_on_dark(rng: random.Random, W: int, H: int) -> tuple[Image.Image, str]:
    """Dark ink on a near-black sheet: a handful of luminance steps of contrast."""
    label = make_label(rng)
    bg = rng.randint(8, 22)
    a = np.zeros((H, W, 3), dtype=np.int16)
    a[:] = bg
    a += rng_np(rng).integers(-2, 3, size=(H, W, 1), dtype=np.int16)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    ink = bg + rng.randint(14, 30)  # deliberately tiny delta
    img = draw_label(img, rng, label, ink=(ink, ink, ink))
    # gentle vignette so the edges sink further
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot(xx - W / 2, yy - H / 2) / math.hypot(W / 2, H / 2)
    b = np.array(img, dtype=np.float32) * (1.0 - 0.25 * r[..., None] ** 2)
    return Image.fromarray(np.clip(b, 0, 255).astype(np.uint8), "RGB"), label


FAMILIES: dict[str, callable] = {
    "snow": fam_snow,
    "spiderweb": fam_spiderweb,
    "split": fam_split,
    "stitch": fam_stitch,
    "strippy": fam_strippy,
    "cut": fam_cut,
    "collage": fam_collage,
    "corrosion": fam_corrosion,
    "cross-shadow": fam_cross_shadow,
    "darts": fam_darts,
    "obstruction": fam_obstruction,
    "dark-on-dark": fam_dark_on_dark,
    # t-ec08 adds "easy" here
}

DEFAULT_SIZE = (640, 180)


def generate_one(family: str, seed: int, index: int = 0,
                 size: tuple[int, int] = DEFAULT_SIZE) -> tuple[Image.Image, str]:
    rng = rng_for(family, seed, index)
    return FAMILIES[family](rng, *size)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def write_dataset(family: str, count: int, seed: int, outdir: Path,
                  size: tuple[int, int]) -> list[dict]:
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    names = [family] if family != "all" else list(FAMILIES)
    for fam in names:
        for i in range(count):
            img, label = generate_one(fam, seed, i, size)
            fname = f"{fam}_{i:03d}.png"
            img.save(outdir / fname)
            rows.append({"file": fname, "label": label, "family": fam,
                         "seed": seed, "index": i})
    with open(outdir / "manifest.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="superocr hard-family generator")
    ap.add_argument("--list", action="store_true", help="list families and exit")
    ap.add_argument("--family", help="family name or 'all'")
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, help="output dir (pngs + manifest.jsonl)")
    ap.add_argument("--size", default="640x180", help="WxH")
    args = ap.parse_args(argv)
    if args.list or not args.family:
        for name in FAMILIES:
            print(name)
        return 0
    W, H = (int(x) for x in args.size.lower().split("x"))
    if args.family != "all" and args.family not in FAMILIES:
        print(f"error: unknown family '{args.family}' (see --list)", file=sys.stderr)
        return 2
    if not args.out:
        img, label = generate_one(args.family, args.seed, 0, (W, H))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        sys.stdout.buffer.write(buf.getvalue())
        print(f"label: {label}", file=sys.stderr)
        return 0
    rows = write_dataset(args.family, args.count, args.seed, args.out, (W, H))
    print(f"wrote {len(rows)} image(s) to {args.out} + manifest.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
