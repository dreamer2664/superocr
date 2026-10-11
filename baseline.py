#!/usr/bin/env python3
"""superocr baseline — the honest floor (t-20261011-65ff).

The classic textbook reader, no ML, no family-specific strategy, no lexicon
rerank, no fallback chain. Contrast normalisation, deskew, per-glyph isolation,
match against rendered fonts. JOBS.md S1: its numbers set what the learned
reader has to beat, so the numbers are published as-is and reproducible from a
clean clone (seeded; reports/ are committed).

Pipeline (one chain for every family and for the reference pack):
    autocontrast -> Otsu -> despeckle -> trim -> deskew (projection-profile
    peak search) -> re-trim -> word/glyph isolation (shared classic
    primitives) -> template match. Nothing else. If it can't be read this
    way, that is a real failure and it goes in the report.

Two findings while building it, both kept in the open:
  * THE METRICS FIX (worth more than any strategy): templates were rendered at
    nominal size CANON_H but compared against glyph masks normalised to
    CANON_H total height — a systematic mismatch with width/aspect that
    misread exact renders of faces that were IN the set (IoU 1.0 when matched
    at native raster scale; e.g. DejaVuSerif-Bold 'r' @ nominal 20). So the
    floor matches glyph masks against face templates rendered at the glyph's
    own raster height (±1px), the textbook way.
  * REJECTED BY MEASUREMENT (kept out): merging adjacent slim fragments of
    over-split glyphs (m -> 1 g 1 1). It glued legitimate i/l/t and dropped
    easy char accuracy 72% -> 56% on n=20. Touching bold/italic glyphs are a
    segmentation war, flagged to S3 — not glued away.

Usage:
    python3 baseline.py image.png                       # one image -> text
    python3 baseline.py --score --count 10 --seed 7     # all families -> table
    python3 baseline.py --reference                     # Carlo's 26 scored tiles
    python3 baseline.py --score --count 10 --seed 7 --out reports/floor.json

stdlib + numpy + Pillow only.
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

import generator as G
import reader as R  # shared classic primitives (otsu/trim/segment/split_wide)

ROOT = Path(__file__).resolve().parent
SAME_SHAPE = set("cCoOsSuUvVwWxXzZ")  # case twins: identical shape, size differs


# --------------------------------------------------------------------------
# native-scale templates — render each face at nominal N, keep the glyph mask
# --------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def _templates_native(nominal: int) -> dict[tuple[str, str], np.ndarray]:
    out = {}
    for face in G.available_fonts():
        try:
            font = ImageFont.truetype(face, nominal)
        except (OSError, TypeError):
            continue
        for ch in R.CHARS:
            im = Image.new("L", (nominal * 3, nominal * 3), 255)
            d = ImageDraw.Draw(im)
            bb = d.textbbox((0, 0), ch, font=font)
            d.text((nominal - bb[0], nominal - bb[1]), ch, font=font, fill=0)
            m = R.trim(np.array(im) < 128)
            if m.any():
                out[(ch, face)] = m
    return out


@functools.lru_cache(maxsize=32)
def _cands_for_height(h: int) -> list[tuple[str, float, np.ndarray]]:
    """All face+char masks whose rendered height is within ±1 of h."""
    cands = []
    for nominal in range(max(10, h), min(72, 2 * h + 4)):
        for (ch, face), t in _templates_native(nominal).items():
            if abs(t.shape[0] - h) <= 1:
                cands.append((ch, face, t))
    return cands


def match_native(mask: np.ndarray) -> tuple[str, float]:
    """Template match at the glyph's own raster height (never upscale-squash)."""
    best = ("?", -1.0)
    for ch, face, t in _cands_for_height(mask.shape[0]):
        s = R._score_glyph(mask, t)
        if s > best[1]:
            best = (ch, s)
    return best


# --------------------------------------------------------------------------
# deskew — projection-profile peak search
# --------------------------------------------------------------------------
def deskew(mask: np.ndarray, max_deg: float = 12.0,
           coarse: float = 1.0, fine: float = 0.2) -> tuple[np.ndarray, float]:
    """Score = std of the row sums; aligned text rows alternate densely
    packed / empty, which maximises it. Coarse then fine. Returns
    (deskewed_mask, applied_degrees)."""
    pil = Image.fromarray((mask * 255).astype(np.uint8))

    def rot(deg: float) -> np.ndarray:
        return np.array(pil.rotate(deg, expand=False, fillcolor=0)) > 0

    def rowstd(m: np.ndarray) -> float:
        return float(m.sum(axis=1).std())

    best_v, best_a = rowstd(rot(0.0)), 0.0
    for deg in np.arange(-max_deg, max_deg + 1e-9, coarse):
        v = rowstd(rot(float(deg)))
        if v > best_v:
            best_v, best_a = v, float(deg)
    for deg in np.arange(best_a - coarse, best_a + coarse + 1e-9, fine):
        v = rowstd(rot(float(deg)))
        if v > best_v:
            best_v, best_a = v, round(float(deg), 1)
    return rot(best_a), best_a


# --------------------------------------------------------------------------
# the floor chain
# --------------------------------------------------------------------------
def read_text(img: Image.Image) -> tuple[str, list[float]]:
    """Contrast norm, deskew, per-glyph isolation, template match.
    Returns (text, per-glyph confidence). Classic only: over-split touching
    glyphs are a reported failure, not glued away (see module docstring)."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.trim(R.despeck(R.otsu(a)))
    if mask.any():
        mask, _ = deskew(mask)
        mask = R.trim(mask)
    words = R.segment(mask)
    out, conf = [], []
    for word in words:
        pieces = []
        for x0, x1 in word:
            for g in R.split_wide(R.trim(mask[:, x0:x1])):
                # arcs/long thin strokes stay: the arc-threshold filter was
                # measured to wipe bold stems (4px @ x-height 10px), so the
                # floor keeps only trivial noise guards
                if g.shape[0] >= 6 and g.sum() >= 10:
                    pieces.append(g)
        if not pieces:
            continue
        cap = max(g.shape[0] for g in pieces)
        chars = []
        for g in pieces:
            ch, s = match_native(g)
            if ch in SAME_SHAPE:
                ch = ch.lower() if g.shape[0] < 0.85 * cap else ch.upper()
            chars.append(ch)
            conf.append(s)
        if chars:
            out.append("".join(chars))
    return " ".join(out), conf


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------
def _char_acc(label: str, text: str) -> float:
    l1, l2 = label.replace(" ", ""), text.replace(" ", "")
    if not l1 and not l2:
        return 1.0
    tot = max(len(l1), len(l2))
    return sum(a == b for a, b in zip(l1, l2)) / tot if tot else 0.0


def score_all(count: int, seed: int, families: list[str] | None = None) -> dict:
    fams = families or list(G.FAMILIES)
    per = []
    exact = cok = n = 0
    easy_exact = easy_n = hard_exact = hard_n = 0
    for fam in fams:
        fx = cok_f = 0.0
        for i in range(count):
            img, label = G.generate_one(fam, seed=seed, index=i)
            text, _ = read_text(img)
            fx += text == label
            cok_f += _char_acc(label, text)
        row = {"family": fam, "n": count,
               "exact": round(fx / count, 4), "char": round(cok_f / count, 4)}
        per.append(row)
        n += count
        exact += fx
        cok += cok_f
        if fam == "easy":
            easy_exact, easy_n = fx, count
        else:
            hard_exact += fx
            hard_n += count
    return {"seed": seed, "count": count,
            "easy_exact": round(easy_exact / max(easy_n, 1), 4),
            "hard_exact": round(hard_exact / max(hard_n, 1), 4),
            "overall_exact": round(exact / max(n, 1), 4),
            "overall_char": round(cok / max(n, 1), 4), "per_family": per}


def score_reference() -> dict:
    """The floor on Carlo's real sheets. Only tiles labelled with certainty
    (scored=true) are measured; '?' tiles are excluded and NAMED, never
    guessed (t-20261011-4e49)."""
    doc = json.loads((ROOT / "reference" / "labels.json").read_text())
    measured, excluded, exact, cok_sum, n = [], [], 0, 0.0, 0
    for t in doc["tiles"]:
        row = {"id": t["id"], "family": t.get("family", "?")}
        if not t.get("scored", False):
            excluded.append({**row, "note": t.get("note", "uncertain")})
            continue
        img = Image.open(ROOT / "reference" / t["file"])
        text, _ = read_text(img)
        ca = _char_acc(t["label"], text)
        measured.append({**row, "label": t["label"], "read": text,
                         "exact": text == t["label"], "char": round(ca, 3)})
        exact += text == t["label"]
        cok_sum += ca
        n += 1
    return {"measured": n, "excluded": len(excluded),
            "exact": round(exact / max(n, 1), 4),
            "char": round(cok_sum / max(n, 1), 4),
            "per_tile": measured, "excluded_tiles": excluded}


def main() -> None:
    ap = argparse.ArgumentParser(description="classic baseline reader (t-20261011-65ff)")
    ap.add_argument("image", nargs="?", help="one image file -> recognised text on stdout")
    ap.add_argument("--score", action="store_true", help="score all generator families")
    ap.add_argument("--reference", action="store_true", help="score Carlo's reference tiles")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--families", default="", help="comma list to restrict --score")
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args()

    if args.score:
        fams = [f for f in args.families.split(",") if f] or None
        rep = score_all(args.count, args.seed, fams)
        print(f"baseline floor — seed {rep['seed']}, {rep['count']} image(s) per family")
        print(f"  easy exact   {rep['easy_exact'] * 100:5.1f}%   (bar: 98)")
        print(f"  hard exact   {rep['hard_exact'] * 100:5.1f}%   (bar: 95)")
        print(f"  overall exact {rep['overall_exact'] * 100:5.1f}%   "
          f"char {rep['overall_char'] * 100:5.1f}%")
        print("  worst families (the honest part of the floor):")
        for r in sorted(rep["per_family"], key=lambda r: r["exact"])[:5]:
            print(f"    {r['family']:<14} exact {r['exact'] * 100:5.1f}%  "
                  f"char {r['char'] * 100:5.1f}%")
    elif args.reference:
        rep = score_reference()
        print(f"reference floor: exact {rep['exact'] * 100:.1f}%  "
              f"char {rep['char'] * 100:.1f}%  on {rep['measured']} scored tiles "
              f"({rep['excluded']} excluded as '?')")
        print("  failures (the gallery, honest):")
        for m in rep["per_tile"]:
            if not m["exact"]:
                print(f"    {m['id']:<24} label={m['label']!r} read={m['read']!r}")
    else:
        if not args.image:
            ap.error("give an image file, or --score / --reference")
        img = Image.open(args.image)
        text, _ = read_text(img)
        print(text)
        return

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")


if __name__ == "__main__":
    main()
