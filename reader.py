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

def _templates_at(h: int) -> dict[tuple[str, str], np.ndarray]:
    """CHARS x face, rendered at CANON_H, ink=True."""
    t: dict[tuple[str, str], np.ndarray] = {}
    for face in G.available_fonts() or ["default"]:
        try:
            font = ImageFont.truetype(face, h) if face != "default" \
                else ImageFont.load_default(size=h)
        except (OSError, TypeError):
            continue
        for ch in CHARS:
            im = Image.new("L", (h * 2, h * 2), 255)
            d = ImageDraw.Draw(im)
            bb = d.textbbox((0, 0), ch, font=font)
            d.text((h - bb[0], h - bb[1]), ch, font=font, fill=0)
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


@functools.lru_cache(maxsize=4)
def _templates(h: int) -> dict[tuple[str, str], np.ndarray]:
    return _templates_at(h)


@functools.lru_cache(maxsize=4)
def _template_grids(h: int) -> dict[tuple[str, str], np.ndarray]:
    return {k: _grid(t) for k, t in _templates_at(h).items()}


def match_glyph(mask: np.ndarray, h: int = CANON_H) -> tuple[str, float]:
    g = _norm(mask, h)
    gg = _grid(g)
    best_ch, best_s = "?", -1.0
    grids = _template_grids(h)
    for (ch, face), t in _templates(h).items():
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


def binarize(resid: np.ndarray, family: str, thr_mult: float = 1.0) -> np.ndarray:
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
        thr = thr_mult * max(6.0 * sigma, 0.25 * float(np.percentile(resid, 99)))
        return despeck(resid > thr)
    return despeck(otsu(resid))




# --------------------------------------------------------------------------
# S2 confidence + fallback chain (t-20261011-d1a6)
# --------------------------------------------------------------------------

LOW_CONF = 0.60  # below this a glyph earns a second attempt


def _boxmean(a: np.ndarray, r: int) -> np.ndarray:
    """Integral-image box blur (edge-padded); O(n) per radius."""
    p = np.pad(a.astype(np.float64), r, mode="edge").cumsum(0).cumsum(1)
    p = np.pad(p, ((1, 0), (1, 0)))
    s = 2 * r + 1
    H, W = a.shape
    return (p[s:s + H, s:s + W] - p[:H, s:s + W]
            - p[s:s + H, :W] + p[:H, :W]) / (s * s)


def local_diff_mask(img: Image.Image, r: int = 25, thr: float = 60.0) -> np.ndarray:
    """Local-contrast binarisation (t-20261012-e199, from barry's be57 probe):
    ink = where the image is darker than its own r-neighbourhood mean by more
    than thr. Band-immune: multiplicative shading and shadow bands sit inside
    the local mean, so they divide out — this is what recovers the shadowed
    rows of cross-shadow that a global threshold loses."""
    a = np.asarray(img.convert("L"), dtype=np.float64)
    return despeck(_boxmean(a, r) - a > thr)


def dark_core_mask(img: Image.Image, tcore: float = 60.0, thi: float = 170.0) -> np.ndarray:
    """Dart-web removal (t-20261012-e199): the darts are semi-transparent grey
    (fill 30-120 at alpha 110-190 over light paper, so blended pixels land
    around 100-160) while the ink is near-black. A dark core (a < tcore)
    therefore contains almost only ink, and ONE regrowth step inside
    (a < thi) recovers the anti-aliased glyph edges without reaching along
    the dart webs (full reconstruction re-captures them: they touch the
    glyphs and are pixel-connected). Measured darts char 0.014 -> 0.689
    (seed 7); holds on seeds 3/11 (0.649/0.698)."""
    a = np.asarray(img.convert("L"), dtype=np.float64)
    grown = np.array(Image.fromarray(
        ((a < tcore) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 127
    return despeck(grown & (a < thi))


def close_mask(mask: np.ndarray, k: int = 1) -> np.ndarray:
    """Morphological closing by k: heals pit gaps up to 2k without a shape
    change bigger than k (corrosion pits chew 1-3px holes out of heavy
    strokes; measured floor 0.166 -> 0.186 on seed-7 tens, t-e199)."""
    im = Image.fromarray((mask * 255).astype(np.uint8))
    for _ in range(k):
        im = im.filter(ImageFilter.MaxFilter(3))
    for _ in range(k):
        im = im.filter(ImageFilter.MinFilter(3))
    return np.array(im) > 127


def _resid_sigma(img: Image.Image, sigma: float) -> np.ndarray:
    """dark-on-dark residual with a tunable background scale: a bigger sigma
    estimates the sheet+vignette more smoothly, absorbing less of the stroke
    itself, and a low threshold then keeps the faint vignette-dimmed strokes
    that sigma 13 / thr 1.0 dropped (measured: char .442 -> .553, seed 7)."""
    a = _lum(img)
    bg = np.array(Image.fromarray(a.astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(sigma)), dtype=np.float32)
    return np.clip(a - bg, 0, None)


def mask_variants(img: Image.Image, family: str) -> list[tuple[str, np.ndarray]]:
    """Primary first; alts are genuinely different preprocessing paths."""
    a = _lum(img)
    if family == "cross-shadow":
        # shadow bands kill every global threshold; the local-contrast mask is
        # band-immune (measured char .075 -> .567 on seed-7 tens, t-e199)
        return [("ld25t60", trim(local_diff_mask(img, 25, 60.0))),
                ("std", trim(otsu(a)))]
    if family == "corrosion":
        # pits chew holes out of heavy strokes: closing heals the small gaps
        return [("close1", trim(close_mask(otsu(a), 1))),
                ("std", trim(otsu(a)))]
    if family == "darts":
        # the dart web is grey, the ink is black: a dark core + one bounded
        # regrow severs the fusion without re-capturing the webs (t-e199)
        return [("dkcore", trim(dark_core_mask(img))),
                ("std", trim(otsu(a)))]
    if family == "dark-on-dark":
        return [("s25t0.5", trim(binarize(_resid_sigma(img, 25), family, 0.5))),
                ("s25t0.7", trim(binarize(_resid_sigma(img, 25), family, 0.7))),
                ("thr1.0", trim(binarize(preprocess(img, family), family, 1.0))),
                ("thr0.7", trim(binarize(preprocess(img, family), family, 0.7)))]
    if family == "obstruction":
        resid = preprocess(img, family)
        return [("thr1.0", trim(binarize(resid, family, 1.0))),
                ("thr0.7", trim(binarize(resid, family, 0.7))),
                ("thr1.4", trim(binarize(resid, family, 1.4)))]
    if family == "split":
        return [("undo", trim(undo_split(trim(otsu(a))))),
                ("raw", trim(otsu(a)))]
    if family == "stitch":
        return [("undo", trim(undo_stitch(img, trim(otsu(a))))),
                ("raw", trim(otsu(a)))]
    if family == "strippy":
        loose = otsu(a) | (a <= 220)
        return [("loose+c3", trim(vclose(trim(loose), 3))),
                ("tight", trim(otsu(a))),
                ("loose+c5", trim(vclose(trim(loose), 5)))]
    if family == "cut":
        return [("c4", trim(vclose(trim(otsu(a)), 4))),
                ("c2", trim(vclose(trim(otsu(a)), 2))),
                ("c6", trim(vclose(trim(otsu(a)), 6)))]
    return [("std", trim(otsu(a)))]


def read_chain(img: Image.Image, family: str) -> tuple[str, list[float], dict]:
    """Instrumented fallback: P1 template match; low-conf glyphs get P2
    (different preprocessing) and P3 (bigger templates); words get P4
    (lexicon rerank). Every adoption is counted so gains are attributable."""
    variants = mask_variants(img, family)
    name0, mask = variants[0]
    stats = {"glyphs": 0, "P2_preproc": 0, "P3_bigger": 0, "P4_rerank": 0}
    SAME_SHAPE = set("cCoOsSuUvVwWxXzZ")
    out, conf = [], []
    for word in segment(mask):
        spans = []
        for x0, x1 in word:
            for g in split_wide(trim(mask[:, x0:x1])):
                spans.append(((x0, x1), g))
        pieces = [((x0, x1), g) for (x0, x1), g in spans
                  if g.shape[0] >= 6 and g.sum() >= 10
                  and g.sum() / max(g.shape) >= 2.2]
        if not pieces:
            continue
        cap = max(g.shape[0] for _, g in pieces)
        chars = []
        for (x0, x1), g in pieces:
            stats["glyphs"] += 1
            ch, s = match_glyph(g)
            stage = "P1"
            if s < LOW_CONF:
                # P2: same columns, different preprocessing
                for _, alt in variants[1:]:
                    ga = trim(alt[:, x0:x1]) if x1 <= alt.shape[1] else None
                    if ga is None or not ga.any():
                        continue
                    for gg in split_wide(ga):
                        if abs(gg.shape[0] - g.shape[0]) > 6:
                            continue
                        ca, sa = match_glyph(gg)
                        if sa > s + 0.02:
                            ch, s, stage = ca, sa, "P2_preproc"
                # P3: bigger templates on the primary glyph
                cb, sb = match_glyph(g, h=40)
                if sb > s + 0.02:
                    ch, s, stage = cb, sb, "P3_bigger"
                if stage != "P1":
                    stats[stage] += 1
            if ch in SAME_SHAPE:
                ch = ch.lower() if g.shape[0] < 0.85 * cap else ch.upper()
            chars.append(ch)
            conf.append(s)
        word_txt = "".join(chars)
        avg = sum(conf[-len(chars):]) / len(chars)
        # P4 fires only for shaky words: confident decodes keep their text,
        # so the lexicon can't overwrite a good read with a near neighbour
        fixed = rerank_word(word_txt) if avg < 0.55 else word_txt
        if fixed != word_txt:
            stats["P4_rerank"] += 1
        out.append(fixed)
    return " ".join(out), conf, stats


def score_chain(family: str, count: int, seed: int) -> dict:
    exact = chars_ok = chars_tot = 0
    stats = {"glyphs": 0, "P2_preproc": 0, "P3_bigger": 0, "P4_rerank": 0}
    for i in range(count):
        img, label = G.generate_one(family, seed=seed, index=i)
        text, _, st = read_chain(img, family)
        for k in stats:
            stats[k] += st[k]
        if text == label:
            exact += 1
        lt, tt = label.replace(" ", ""), text.replace(" ", "")
        for a, b in zip(lt, tt):
            chars_tot += 1
            chars_ok += a == b
        chars_tot += abs(len(lt) - len(tt))
    base = score(family, count, seed)
    chained = exact / count if count else 0.0
    return {"family": family, "n": count, "seed": seed,
            "chain_exact": chained, "chain_char": chars_ok / chars_tot if chars_tot else 0.0,
            "baseline_exact": base["exact_acc"], "baseline_char": base["char_acc"],
            "stages": stats}


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
    if family in ("cross-shadow", "dark-on-dark", "darts", "corrosion"):
        # band/vignette/dart-web walls: mask_variants carries the measured
        # primaries (local-contrast / big-sigma residuals / dark-core) and
        # read_chain adopts a different variant glyph-by-glyph when it
        # scores better (t-e199)
        text, conf, _ = read_chain(img, family)
        return text, conf
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
        a = _lum(img)
        if family in ("dark-on-dark", "obstruction"):
            mask = trim(binarize(preprocess(img, family), family))
        else:  # easy and friends: clean sheet, straight Otsu
            mask = trim(otsu(a))
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


def split_wide_marked(mask: np.ndarray, depth: int = 0,
                      forced: bool = False) -> list[tuple[np.ndarray, bool]]:
    """split_wide carrying cut metadata (t-20261011-31af): `forced` marks that
    the valley at the split column carried ink, i.e. the cut passed through a
    stroke (an M cut between its legs) rather than through whitespace (a true
    glyph boundary like i|l). The plain splitter cannot tell the two apart and
    happily halves a heavy wide glyph; the halves then template-match as
    plausible narrow letters ('M' -> 'AI')."""
    h, w = mask.shape
    if depth >= 3 or w <= 1.35 * h or w < 8:
        return [(mask, forced)] if mask.any() else []
    mid = slice(int(w * 0.2), int(w * 0.8))
    colsum = mask.sum(axis=0)
    x = int(np.argmin(colsum[mid])) + int(w * 0.2)
    cut_forced = bool(colsum[x] > 0)
    left, right = trim(mask[:, :x]), trim(mask[:, x:])
    out: list[tuple[np.ndarray, bool]] = []
    if left.any():
        out += split_wide_marked(left, depth + 1, forced)
    if right.any():
        out += split_wide_marked(right, depth + 1, cut_forced)
    return out


def merge_forced(marked: list[tuple[np.ndarray, bool]]) -> list[np.ndarray]:
    """Merge a piece back into its left neighbour only when its cut was forced
    AND the merged glyph matches at least as well as the better part (small
    margin: local noise must not undo a genuine through-stroke merge). Clean
    whitespace boundaries are never candidates, so the arbiter only ever
    judges splits that went through ink."""
    changed = True
    while changed and len(marked) > 1:
        changed = False
        for j in range(1, len(marked)):
            (a, _), (b, cut_forced) = marked[j - 1], marked[j]
            if not cut_forced:
                continue
            H, W = max(a.shape[0], b.shape[0]), a.shape[1] + b.shape[1]
            m = np.zeros((H, W), bool)
            m[:a.shape[0], :a.shape[1]] |= a
            m[:b.shape[0], a.shape[1]:a.shape[1] + b.shape[1]] |= b
            m = trim(m)
            if not m.any():
                continue
            _, s_m = match_glyph(m)
            _, s_a = match_glyph(a)
            _, s_b = match_glyph(b)
            if s_m >= max(s_a, s_b) - 0.06:
                marked[j - 1:j + 1] = [(m, False)]
                changed = True
                break
    return [p for p, _ in marked]


def split_wide(mask: np.ndarray, depth: int = 0) -> list[np.ndarray]:
    """Touching glyphs arrive as one wide blob: cut at the sparsest column,
    then re-merge through-stroke cuts when the merged glyph matches at least
    as well (t-20261011-31af; keeps genuine boundaries like 'il' split)."""
    return merge_forced(split_wide_marked(mask, depth))


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
    ap.add_argument("--chain", action="store_true")
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    if args.chain:
        r = score_chain(args.family, args.count, args.seed)
        print(json.dumps(r, indent=1))
        return 0
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
