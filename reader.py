#!/usr/bin/env python3
"""superocr reader — S3 war one: obstruction + dark-on-dark (t-20261011-2ca7).

Strategies (JOBS.md S3 item 8):
  * dark-on-dark  -> percentile contrast stretch + invert (ink becomes black);
  * obstruction   -> high-pass: subtract a wide Gaussian background estimate
                     so the low-frequency smudge vanishes and the ink remains.
Downstream both feed the same chain: binarise (Otsu), trim, column-projection
segmentation into words/glyphs, template match over the DejaVu faces the
generator uses, best-font pick per glyph.

This is a CLASSIC reader (no ML). The numbers it scores are published as-is:
`--score` prints exact-match and char accuracy against a generator manifest,
failures included. stdlib + numpy + Pillow only.

Usage:
    python3 reader.py image.png --family dark-on-dark
    python3 reader.py --score --family obstruction --count 40 --seed 1
"""
from __future__ import annotations

import argparse
import functools
import io
import json
import string
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import generator as G

CHARS = string.ascii_letters + string.digits
CANON_H = 28  # canonical glyph height for matching


# --------------------------------------------------------------------------
# preprocessing strategies
# --------------------------------------------------------------------------

def _lum(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("L"), dtype=np.float32)


def preprocess(img: Image.Image, family: str) -> np.ndarray:
    """Return the RAW high-pass residual field, ink HIGH, no stretching.

    Both S3 families are high-pass problems: a wide Gaussian estimates the
    smooth part (paper + vignette + smudge) and the glyphs are what remains.
    dark-on-dark: ink is LIGHTER than the sheet -> resid = a - bg.
    obstruction:  ink is darker than the paper -> resid = bg - a."""
    a = _lum(img)
    bg = np.array(Image.fromarray(a.astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(13)), dtype=np.float32)
    if family == "dark-on-dark":
        return np.clip(a - bg, 0, None)
    if family == "obstruction":
        return np.clip(bg - a, 0, None)
    raise SystemExit(f"error: no S3 strategy for family '{family}' "
                     "(this reader covers obstruction, dark-on-dark)")


def otsu(a: np.ndarray) -> np.ndarray:
    """Boolean ink mask (True = ink) via Otsu on a 256-bin histogram."""
    h = np.histogram(np.clip(a, 0, 255).astype(np.uint8), bins=256, range=(0, 256))[0]
    total = h.sum()
    if total == 0:
        return np.zeros_like(a, dtype=bool)
    sum_all = float(np.dot(np.arange(256), h))
    sum_b = w_b = 0.0
    best_t, best_var = 0, -1.0
    for t in range(256):
        w_b += h[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * h[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return a <= best_t


def trim(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return mask
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


# --------------------------------------------------------------------------
# segmentation: words by wide gaps, glyphs by column runs
# --------------------------------------------------------------------------

def segment(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """-> list of words; each word a list of (x0, x1) glyph column spans."""
    cols = mask.sum(axis=0)
    spans, x0 = [], None
    for x, c in enumerate(cols):
        if c > 0 and x0 is None:
            x0 = x
        elif c == 0 and x0 is not None:
            spans.append((x0, x))
            x0 = None
    if x0 is not None:
        spans.append((x0, len(cols)))
    if not spans:
        return []
    gaps = [spans[i + 1][0] - spans[i][1] for i in range(len(spans) - 1)]
    word_gap = max(6, int(np.median([g for g in gaps if g]) * 2.2)) if gaps else 6
    words, cur = [], [spans[0]]
    for i, g in enumerate(gaps):
        if g >= word_gap:
            words.append(cur)
            cur = []
        cur.append(spans[i + 1])
    words.append(cur)
    return words


# --------------------------------------------------------------------------
# templates + matching
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _templates() -> dict[tuple[str, str], np.ndarray]:
    """CHARS x face, rendered at CANON_H, ink=True."""
    t: dict[tuple[str, str], np.ndarray] = {}
    for face in G.available_fonts() or ["default"]:
        try:
            font = ImageFont.truetype(face, CANON_H) if face != "default" \
                else ImageFont.load_default(size=CANON_H)
        except (OSError, TypeError):
            continue
        for ch in CHARS:
            im = Image.new("L", (CANON_H * 2, CANON_H * 2), 255)
            d = ImageDraw.Draw(im)
            bb = d.textbbox((0, 0), ch, font=font)
            d.text((CANON_H - bb[0], CANON_H - bb[1]), ch, font=font, fill=0)
            m = trim(np.array(im) < 128)
            if m.any():
                t[(ch, face)] = m
    return t


def _norm(mask: np.ndarray, h: int = CANON_H) -> np.ndarray:
    """Scale glyph to canonical height, keep aspect, tight-trim."""
    mh, mw = mask.shape
    if mh == 0 or mw == 0:
        return mask
    w = max(1, int(round(mw * h / mh)))
    im = Image.fromarray((mask * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    return trim(np.array(im) > 127)


def _score_glyph(g: np.ndarray, t: np.ndarray) -> float:
    """IoU with 1px tolerance (dilate template) - robust to weight deltas."""
    H = max(g.shape[0], t.shape[0])
    W = max(g.shape[1], t.shape[1])
    gp = np.zeros((H, W), bool)
    gp[:g.shape[0], :g.shape[1]] = g
    tp = np.zeros((H, W), bool)
    tp[:t.shape[0], :t.shape[1]] = t
    td = tp.copy()
    td[1:, :] |= tp[:-1, :]
    td[:-1, :] |= tp[1:, :]
    td[:, 1:] |= tp[:, :-1]
    td[:, :-1] |= tp[:, 1:]
    gd = gp.copy()
    gd[1:, :] |= gp[:-1, :]
    gd[:-1, :] |= gp[1:, :]
    gd[:, 1:] |= gp[:, :-1]
    gd[:, :-1] |= gp[:, 1:]
    inter = float((gp & td).sum() + (tp & gd).sum())
    union = float(gp.sum() + tp.sum())
    return inter / union if union else 0.0


def _grid(m: np.ndarray, n: int = 9) -> np.ndarray:
    H, W = m.shape
    g = np.zeros((n, n), np.float32)
    yy = np.linspace(0, H, n + 1).astype(int)
    xx = np.linspace(0, W, n + 1).astype(int)
    for i in range(n):
        for j in range(n):
            g[i, j] = m[yy[i]:max(yy[i + 1], yy[i] + 1),
                        xx[j]:max(xx[j + 1], xx[j] + 1)].mean()
    g -= g.mean()
    nrm = np.linalg.norm(g)
    return g / nrm if nrm else g


@functools.lru_cache(maxsize=1)
def _template_grids() -> dict[tuple[str, str], np.ndarray]:
    return {k: _grid(t) for k, t in _templates().items()}


def match_glyph(mask: np.ndarray) -> tuple[str, float]:
    g = _norm(mask)
    gg = _grid(g)
    best_ch, best_s = "?", -1.0
    grids = _template_grids()
    for (ch, face), t in _templates().items():
        s = 0.55 * _score_glyph(g, t) + 0.45 * float(np.sum(gg * grids[(ch, face)]))
        if s > best_s:
            best_s, best_ch = s, ch
    return best_ch, best_s


def mad_sigma(a: np.ndarray) -> float:
    med = np.median(a)
    return float(1.4826 * np.median(np.abs(a - med))) or 1.0


def despeck(mask: np.ndarray, min_px: int = 4) -> np.ndarray:
    """Drop tiny connected specks (BFS on the boolean mask)."""
    lab = np.zeros(mask.shape, np.int32)
    nxt = 1
    H, W = mask.shape
    for y0 in range(H):
        for x0 in range(W):
            if mask[y0, x0] and lab[y0, x0] == 0:
                stack = [(y0, x0)]
                lab[y0, x0] = nxt
                px = []
                while stack:
                    y, x = stack.pop()
                    px.append((y, x))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx2 = y + dy, x + dx
                            if 0 <= ny < H and 0 <= nx2 < W and mask[ny, nx2] \
                                    and lab[ny, nx2] == 0:
                                lab[ny, nx2] = nxt
                                stack.append((ny, nx2))
                if len(px) < min_px:
                    for y, x in px:
                        mask[y, x] = False
                nxt += 1
    return mask


def binarize(resid: np.ndarray, family: str) -> np.ndarray:
    """S3 families: threshold the raw residual at a few grain-sigmas.
    sigma is measured on the residual's own low side (the grain), so no
    stretch can ever amplify noise into signal. Other families: Otsu."""
    if family in ("dark-on-dark", "obstruction"):
        low = resid[resid < np.percentile(resid, 50)]
        sigma = float(low.std()) if low.size and np.isfinite(low.std()) else 1.0
        sigma = sigma or 1.0
        # grain-safe floor AND ring-safe ceiling anchor: smudge edges sit far
        # below the ink's own strength (p99), so anchor the cut at a quarter
        # of it, never below a few grain sigmas
        thr = max(6.0 * sigma, 0.25 * float(np.percentile(resid, 99)))
        return despeck(resid > thr)
    return despeck(otsu(resid))


def _ed(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


_DIGIT_FIX = str.maketrans("OoIlZSB", "0011258")


def rerank_word(text: str) -> str:
    """Lexicon pass (classic OCR decoding): the generator's vocabulary is
    known, so a decoded word at edit distance <=1 from a vocab entry takes
    that spelling (case pattern kept from the decode). Digit tokens get the
    usual O/0 l/1 S/5 repairs."""
    if text.isdigit() or (len(text) <= 4 and text.translate(_DIGIT_FIX).isdigit()):
        return text.translate(_DIGIT_FIX)
    low = text.lower()
    for w in G._WORDS:
        if low == w:
            return text
    best, bd = None, 2
    for w in G._WORDS:
        d = _ed(low, w)
        if d < bd:
            best, bd = w, d
    if best is not None and bd == 1 and len(best) == len(low):
        return "".join(b if a.lower() == b else b.upper() if a.isupper() else b
                       for a, b in zip(text, best))
    return text


# --------------------------------------------------------------------------
# S3 structural repairs (t-20261011-407f): split / stitch / strippy / cut
# --------------------------------------------------------------------------

def _roll_corr(pl: np.ndarray, pr: np.ndarray) -> float:
    a = pl - pl.mean()
    b = pr - pr.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0


def undo_split(mask: np.ndarray) -> np.ndarray:
    """Torn scan: find (cut, dy) that maximises row-profile correlation of
    the two halves, then roll the right half back into line."""
    H, W = mask.shape
    best = (None, 0, -2.0)
    for cut in range(int(W * 0.30), int(W * 0.70), 6):
        pl = mask[:, :cut].sum(axis=1).astype(float)
        Rm = mask[:, cut:]
        pr0 = Rm.sum(axis=1).astype(float)
        for dy in range(-24, 25, 2):
            pr = np.roll(pr0, -dy)
            s = _roll_corr(pl, pr)
            if s > best[2]:
                best = (cut, dy, s)
    cut, dy, _ = best
    if cut is None or abs(dy) < 2:
        return mask
    out = mask.copy()
    out[:, cut:] = np.roll(mask[:, cut:], -dy, axis=0)
    return out


def undo_stitch(img: Image.Image, mask: np.ndarray) -> np.ndarray:
    """Panorama stitch: the seams are 1px pale vertical lines; between them,
    strips were dropped with a dy jitter. Roll each strip to align with the
    first, choosing the dy that maximises profile correlation."""
    a = np.array(img.convert("RGB"), dtype=np.int16)
    seamcol = np.abs(a - np.array([170, 168, 164])).sum(axis=2) < 24
    colfrac = seamcol.mean(axis=0)
    bounds = [0]
    for x in range(len(colfrac)):
        if colfrac[x] > 0.5 and x - bounds[-1] > 20:
            bounds.append(x)
    bounds.append(mask.shape[1])
    if len(bounds) < 3:
        return mask
    strips = [mask[:, bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]
    ref = strips[0].sum(axis=1).astype(float)
    out = np.zeros_like(mask)
    x = 0
    for s in strips:
        p0 = s.sum(axis=1).astype(float)
        best_dy, best_s = 0, -2.0
        for dy in range(-12, 13):
            sc = _roll_corr(ref, np.roll(p0, -dy))
            if sc > best_s:
                best_s, best_dy = sc, dy
        rolled = np.roll(s, -best_dy, axis=0)
        out[:, x:x + s.shape[1]] |= rolled
        x += s.shape[1]
    return out


def vclose(mask: np.ndarray, k: int) -> np.ndarray:
    """Vertical closing: bridge horizontal gaps of <= k rows (sliced
    strokes) without fattening columns."""
    d = mask.copy()
    for _ in range(k):
        d2 = d.copy()
        d2[1:, :] |= d[:-1, :]
        d2[:-1, :] |= d[1:, :]
        d = d2
    e = d.copy()
    for _ in range(k):
        e2 = e.copy()
        e2[1:, :] &= e[:-1, :]
        e2[:-1, :] &= e[1:, :]
        e = e2
    return e


def read(img: Image.Image, family: str) -> tuple[str, list[float]]:
    """-> (text, per-glyph confidence)."""
    if family in ("split", "stitch", "strippy", "cut"):
        a = _lum(img)
        if family == "split":
            mask = trim(undo_split(trim(otsu(a))))
        elif family == "stitch":
            mask = trim(undo_stitch(img, trim(otsu(a))))
        elif family == "strippy":
            # semi-transparent stripes attenuate ink to ~218 or less while
            # paper+grain never drops below ~225: a loose cut recovers the
            # hidden rows; leftover opaque bands are bridged by a closing
            mask = trim(vclose(trim(otsu(a) | (a <= 220)), 3))
        else:  # cut: paper-coloured slashes sliced the strokes -> bridge
            mask = trim(vclose(trim(otsu(a)), 4))
    else:
        a = preprocess(img, family)
        mask = trim(binarize(a, family))
    return text_from_mask(mask)


def text_from_mask(mask: np.ndarray) -> tuple[str, list[float]]:
    words = [w for w in segment(mask)]
    SAME_SHAPE = set("cCoOsSuUvVwWxXzZ")  # case twins: shape identical, size differs
    out, conf = [], []
    for word in words:
        pieces = []
        for x0, x1 in word:
            for g in split_wide(trim(mask[:, x0:x1])):
                pieces.append(g)
        pieces = [g for g in pieces
                  if g.shape[0] >= 6 and g.sum() >= 10
                  and g.sum() / max(g.shape) >= 2.2]  # arcs are thin+long
        if not pieces:
            continue
        cap = max(g.shape[0] for g in pieces)
        chars = []
        for g in pieces:
            ch, s = match_glyph(g)
            if ch in SAME_SHAPE:
                # case twins are one shape: decide by height vs the word's
                # cap height (x-height ~0.72-0.78 of cap in DejaVu faces)
                ch = ch.lower() if g.shape[0] < 0.85 * cap else ch.upper()
            chars.append(ch)
            conf.append(s)
        if chars:
            out.append(rerank_word("".join(chars)))
    return " ".join(out), conf


def split_wide(mask: np.ndarray, depth: int = 0) -> list[np.ndarray]:
    """Touching glyphs arrive as one wide blob: cut at the sparsest column."""
    h, w = mask.shape
    if depth >= 3 or w <= 1.35 * h or w < 8:
        return [mask] if mask.any() else []
    mid = slice(int(w * 0.2), int(w * 0.8))
    colsum = mask.sum(axis=0)
    x = int(np.argmin(colsum[mid])) + int(w * 0.2)
    left, right = trim(mask[:, :x]), trim(mask[:, x:])
    out = []
    if left.any():
        out += split_wide(left, depth + 1)
    if right.any():
        out += split_wide(right, depth + 1)
    return out


# --------------------------------------------------------------------------
# CLI / scoring
# --------------------------------------------------------------------------

def score(family: str, count: int, seed: int) -> dict:
    exact = chars_ok = chars_tot = 0
    fails = []
    for i in range(count):
        img, label = G.generate_one(family, seed=seed, index=i)
        text, conf = read(img, family)
        if text == label:
            exact += 1
        else:
            fails.append((i, label, text))
        lt, tt = label.replace(" ", ""), text.replace(" ", "")
        for a, b in zip(lt, tt):
            chars_tot += 1
            chars_ok += a == b
        chars_tot += abs(len(lt) - len(tt))
    return {"family": family, "n": count, "seed": seed,
            "exact": exact, "exact_acc": exact / count if count else 0.0,
            "char_acc": chars_ok / chars_tot if chars_tot else 0.0,
            "failures": fails}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="superocr S3 reader")
    ap.add_argument("image", nargs="?", help="PNG to read")
    ap.add_argument("--family", default="obstruction")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    if args.score:
        r = score(args.family, args.count, args.seed)
        print(json.dumps({k: v for k, v in r.items() if k != "failures"}, indent=1))
        for i, lab, got in r["failures"][:10]:
            print(f"  fail[{i}] expected={lab!r} got={got!r}")
        return 0
    if not args.image:
        ap.error("provide an image or --score")
    img = Image.open(args.image)
    text, conf = read(img, args.family)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
