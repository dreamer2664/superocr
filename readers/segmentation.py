#!/usr/bin/env python3
"""segmentation.py — minimal, honest glyph segmentation (t-20261011-f0d2).

Not the S1 product (t-20261011-65ff owns the classic reader). This is the
smallest segmenter that lets a glyph classifier be measured end to end:

    image -> ink polarity + Otsu binarisation -> coarse deskew
          -> text bands (lines) -> word/glyph boxes, left to right

Everything is deterministic, numpy + PIL only, and each step is a plain
function so the S3 tasks can replace one without touching the others.

Deliberate limits (documented rather than hidden): touching letters are split
by valley search and will sometimes split wrongly; heavy structural damage
(split/stitch/strippy) is S3 territory; multi-line labels are supported,
columns of text are not.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

GLYPH_H = 24          # classifier input height
GLYPH_W = 24          # classifier input width


def to_gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float64)


def stretch(gray: np.ndarray) -> np.ndarray:
    """Contrast stretch to 0..255, robust to a tiny ink footprint.

    Percentiles 2/98 are the workhorse, but a clean image with very little
    text can put BOTH percentiles on the background (measured: a 640x180
    sheet with a single line gave p2=p98=252), which silently collapsed the
    scale. When the percentile window is degenerate, fall back to the true
    tails; when even those agree, the image is flat and ink is nothing.
    """
    lo, hi = np.percentile(gray, 2), np.percentile(gray, 98)
    if hi - lo < 8.0:
        lo, hi = float(gray.min()), float(gray.max())
    if hi - lo < 1e-6:
        return np.full_like(gray, 0.0)
    return (gray - lo) / (hi - lo) * 255.0


def otsu(gray: np.ndarray) -> float:
    """Otsu's threshold on a 0..255 image (vectorised, deterministic)."""
    hist, _ = np.histogram(gray, bins=256, range=(0, 255))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 127.0
    omega = np.cumsum(hist) / total
    mu = np.cumsum(hist * np.arange(256)) / total
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    denom[denom == 0] = 1e-12
    sigma_b = (mu_t * omega - mu) ** 2 / denom
    return float(np.argmax(sigma_b))


def ink_mask(img: Image.Image) -> np.ndarray:
    """Boolean mask, True where ink is — polarity decided from the image.

    Ink is made the BRIGHT side first (invert when the background is light,
    which is the common case), then Otsu separates bright ink from a dark
    background. Getting this backwards selects the background as ink, which
    is exactly the bug this docstring now prevents.
    """
    gray = to_gray(img)
    # polarity from the RAW tones, before any stretching: a stretched image
    # is centred on zero and the mean test would be meaningless on it
    if float(gray.mean()) >= 128.0:        # light background: ink is the dark side
        gray = 255.0 - gray
    gray = stretch(gray)
    threshold = otsu(gray)
    return gray > threshold


def _projection_variance(mask: np.ndarray) -> float:
    rows = mask.sum(axis=1)
    return float(np.var(rows))


def deskew(mask: np.ndarray, limit: float = 8.0, coarse: float = 1.0,
           fine: float = 0.25) -> tuple[np.ndarray, float]:
    """Rotate so text rows are horizontal; chosen by row-profile variance."""
    img = Image.fromarray((mask * 255).astype(np.uint8))

    w0, h0 = img.size

    def rotate_back(angle: float) -> np.ndarray:
        """Rotate, then crop to the original frame.

        Without the crop, expand=True grows the canvas with black corners and
        the row-variance score grows monotonically with |angle| - the optimum
        then sits at the search limit for every image, which is how a deskew
        becomes a no-op that looks confident.
        """
        rot = img.rotate(angle, resample=Image.BILINEAR, expand=True, fillcolor=0)
        rw, rh = rot.size
        left = (rw - w0) // 2
        top = (rh - h0) // 2
        return np.asarray(rot.crop((left, top, left + w0, top + h0))) > 127

    def score(angle: float) -> float:
        return _projection_variance(rotate_back(angle))

    best_angle = 0.0
    best = score(0.0)
    for angle in np.arange(-limit, limit + 1e-9, coarse):
        s = score(float(angle))
        if s > best:
            best, best_angle = s, float(angle)
    for angle in np.arange(best_angle - coarse, best_angle + coarse + 1e-9, fine):
        s = score(float(angle))
        if s > best:
            best, best_angle = s, float(angle)
    if abs(best_angle) < 1e-9:
        return mask, 0.0
    rot = Image.fromarray((mask * 255).astype(np.uint8)).rotate(
        best_angle, resample=Image.BILINEAR, expand=True, fillcolor=0)
    return np.asarray(rot) > 127, best_angle


def _runs(flags: np.ndarray, min_run: int = 1) -> list[tuple[int, int]]:
    """Contiguous True runs in a 1-D boolean array -> (start, end) inclusive."""
    out: list[tuple[int, int]] = []
    start = None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_run:
                out.append((start, i - 1))
            start = None
    if start is not None and len(flags) - start >= min_run:
        out.append((start, len(flags) - 1))
    return out


def text_bands(mask: np.ndarray, min_ink_frac: float = 0.004,
               merge_gap: int = 2) -> list[tuple[int, int]]:
    """Horizontal bands containing text (candidate lines)."""
    row_ink = mask.sum(axis=1)
    if mask.size == 0:
        return []
    thresh = max(1.0, min_ink_frac * mask.shape[1])
    bands = _runs(row_ink > thresh, min_run=2)
    merged: list[list[int]] = []
    for b in bands:
        if merged and b[0] - merged[-1][1] <= merge_gap + 1:
            merged[-1][1] = b[1]
        else:
            merged.append([b[0], b[1]])
    return [(a, b) for a, b in merged]


def glyph_boxes(mask: np.ndarray, band: tuple[int, int],
                word_gap_frac: float = 0.32,
                split_wide_frac: float = 1.45) -> list[tuple[int, int, int, int, bool]]:
    """Split one band into glyph boxes left to right.

    Returns (x0, y0, x1, y1, space_before). Words are separated at gaps wider
    than word_gap_frac * band height; over-wide letter groups are split at the
    deepest column valley (touching letters).
    """
    y0, y1 = band
    strip = mask[y0:y1 + 1, :]
    height = max(1, y1 - y0 + 1)
    col_ink = strip.sum(axis=0)
    runs = _runs(col_ink > 0, min_run=1)
    if not runs:
        return []
    boxes: list[tuple[int, int, int, int, bool]] = []
    space_gap = word_gap_frac * height
    prev_end = None
    for (a, b) in runs:
        space_before = prev_end is not None and (a - prev_end) >= space_gap
        width = b - a + 1
        if width > split_wide_frac * height and width >= 6:
            # find the deepest valley near the middle and cut there
            mid_lo = a + int(0.25 * width)
            mid_hi = b - int(0.25 * width)
            if mid_hi <= mid_lo:
                boxes.append((a, y0, b, y1, space_before))
            else:
                valley = int(np.argmin(col_ink[mid_lo:mid_hi + 1])) + mid_lo
                pieces = []
                for (x0, x1) in ((a, valley), (valley + 1, b)):
                    sub = _tight_rows(strip[:, x0:x1 + 1], y0)
                    if sub is not None:
                        pieces.append((x0, sub[0], x1, sub[1]))
                for i, (x0, ty0, x1, ty1) in enumerate(pieces):
                    boxes.append((x0, ty0, x1, ty1, space_before if i == 0 else False))
        else:
            sub = _tight_rows(strip[:, a:b + 1], y0)
            if sub is not None:
                boxes.append((a, sub[0], b, sub[1], space_before))
        prev_end = b
    return boxes


def _tight_rows(columns: np.ndarray, y_offset: int) -> tuple[int, int] | None:
    """Tight vertical extent of ink inside a column slice, absolute coords."""
    rows = columns.sum(axis=1)
    run = _runs(rows > 0, min_run=1)
    if not run:
        return None
    return y_offset + run[0][0], y_offset + run[-1][1]


def normalise_glyph(mask: np.ndarray, box: tuple[int, int, int, int],
                    out_h: int = GLYPH_H, out_w: int = GLYPH_W) -> np.ndarray:
    """Crop a glyph and scale it into a fixed-size float32 image in [0, 1]."""
    x0, y0, x1, y1 = box
    crop = mask[y0:y1 + 1, x0:x1 + 1]
    if crop.size == 0:
        return np.zeros((out_h, out_w), dtype=np.float32)
    img = Image.fromarray((crop * 255).astype(np.uint8))
    h, w = crop.shape
    scale = min(out_w / w, out_h / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    img = img.resize((new_w, new_h), Image.BILINEAR)
    canvas = Image.new("L", (out_w, out_h), 0)
    canvas.paste(img, ((out_w - new_w) // 2, (out_h - new_h) // 2))
    return (np.asarray(canvas, dtype=np.float32) / 255.0)


def analyse(img: Image.Image):
    """Full pipeline: image -> (deskewed ink mask, ordered glyph boxes).

    Boxes are (x0, y0, x1, y1) with a space_before flag; the first box of every
    band after the first is forced to space_before=True, because a new line
    means the words are not adjacent text.
    """
    mask = ink_mask(img)
    mask, _ = deskew(mask)
    out: list[tuple[tuple[int, int, int, int], bool]] = []
    for bi, band in enumerate(text_bands(mask)):
        for gi, (x0, y0, x1, y1, space) in enumerate(glyph_boxes(mask, band)):
            if bi > 0 and gi == 0:
                space = True
            out.append(((x0, y0, x1, y1), space))
    return mask, out


def segment(img: Image.Image) -> list[tuple[tuple[int, int, int, int], bool]]:
    """Convenience: analyse() without the mask."""
    return analyse(img)[1]
