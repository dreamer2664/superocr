#!/usr/bin/env python3
"""readers/collage.py — the tiled-sheet route (S14, t-20261012-1d17).

The collage family in one paragraph: several small *cards* (each a rotated,
bright rectangle carrying one line of dark text) pasted over a 28-px patchwork
of grey tiles. Rotating a card leaves black WEDGE BARS along its edges, and
adjacent cards can touch. Whole-image binarisation drowns in the patchwork
(every path scored 0.000 on this family in the S11 screens), so this module
reads the sheet the way a person does: find each card, straighten it, read it
on its own, then read the cards left to right.

Why the detector works (each rule earned in the S14 ladder):
  * cards are painted 235-250, tiles top out at 235  -> a STRICT >=236
    threshold yields the card BODY un-inflated. (A 41-px median filter locates
    cards but inflates each by ~20 px, dragging the neighbour's text in.)
  * a component is split at a wedge bar ONLY: a dark column (mean >= 0.7 in the
    component window) whose longest dark run is >= 1.12x the text band. Glyph
    stems are dark columns too, but never taller than the band - that check is
    what stops the over-splitting that produced 'bfa ini iml iqi'.
  * the reading engine is the glyph CNN (readers/cnn_reader.py). The floor's
    baseline.read_text collapses on +-9 deg cards ('Beacon' -> 'mkUK'; even a
    5 deg rotation of a clean easy image reads 'DH0 Keej'), and rectification
    keeps 8-connected glyph handling intact - measured head to head.

Reading furniture, in order: ink-bbox trim -> strip_trim (full rows/cols that
are >=60% dark: card border lines and wedge slivers) -> edge_prune (short
slivers hugging the left/right rim that are taller than the x-height band or
knife-thin) -> 3x LANCZOS -> cnn_reader.read_image. The 3-px inset after all
trims is what removed the last rim chrome ('r BeaConJ' -> 'BeaCon').

Measured (seed-1 official 8 + held-out seed-7 n=10, scale 3):
    official  mean char 0.746   (whole-image floor: 0.000)
    seed-7    mean char 0.782   exact 2/10
Exact-match cells are still 0 on the official set: the residue is per-glyph
case (c/C, i/I/l) and occasional rim chrome, not detection. Those stay open.

Two rectification paths, and the difference is material - stated in full:
  * cv2 present (the sandbox, most dev boxes): minAreaRect + warpPerspective,
    INTER_CUBIC - the configuration every number below was measured on.
  * cv2 absent (this repo's CI installs numpy+Pillow only): a numpy/PIL
    fallback - minimum-area rectangle by 0.5-degree angle sweep + PIL affine
    straightening. Same detector, same reading furniture; measured ~0.60 mean
    char on the official 8 (the warp sampling costs ~0.15 char against the cv2
    path). It is a fallback, not the claimed number.

Deterministic either way: same image + same path -> same text.

    python3 readers/collage.py --image data/hard/images/collage-0000.png
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:                 # cnn_reader sits next to us
    sys.path.insert(0, str(_HERE))
import cnn_reader as CR  # noqa: E402

try:                                           # optional fast path, see docstring
    import cv2
except Exception:                              # pragma: no cover - environment
    cv2 = None

STRICT = 236          # card body >= this; patchwork tiles top out at 235
DARK = 90             # ink and wedge bars
MIN_DARK_ROW = 2      # band rows need >= this many dark component pixels
SPLIT_DARK_FRAC = 0.7
WEDGE_RUN = 1.12      # split only when the dark column is taller than the band
MIN_AREA, MIN_W, MIN_H = 900, 24, 14
MIN_BLOCK_W, MIN_BLOCK_PX = 20, 400
INSET = 3             # rim inset after the trims (kills leftover edge chrome)
SCALE = 3             # LANCZOS upscale before the CNN
SINGLE_BLOCK_COVER = 0.6   # one block this big == the whole sheet, not a card


# ---------------------------------------------------------------- plumbing

def _components(mask: np.ndarray) -> list[dict]:
    """8-connected components; pixels kept (PCA needs them). Plain Python on
    purpose: numpy+PIL only, and the masks here are small (one sheet)."""
    ys_all, xs_all = np.nonzero(mask)
    if len(ys_all) == 0:
        return []
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    out = []
    for sy, sx in zip(ys_all.tolist(), xs_all.tolist()):
        if visited[sy, sx]:
            continue
        stack = [(sy, sx)]
        visited[sy, sx] = True
        py, px = [], []
        while stack:
            y, x = stack.pop()
            py.append(y)
            px.append(x)
            for dy in (-1, 0, 1):
                ny = y + dy
                if ny < 0 or ny >= height:
                    continue
                for dx in (-1, 0, 1):
                    nx = x + dx
                    if nx < 0 or nx >= width or visited[ny, nx] or not mask[ny, nx]:
                        continue
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        ys = np.array(py, dtype=np.int32)
        xs = np.array(px, dtype=np.int32)
        out.append({"area": len(ys), "x0": int(xs.min()), "x1": int(xs.max()),
                    "y0": int(ys.min()), "y1": int(ys.max()), "ys": ys, "xs": xs})
    return out


def _longest_run(col: np.ndarray) -> int:
    best = cur = 0
    for v in col.tolist():
        cur = cur + 1 if v else 0
        if cur > best:
            best = cur
    return best


def _min_area_rect(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float, float, float, float]:
    """Rotating-calipers minimum-area rectangle -> (cx, cy, w, h, ang), where
    `ang` is the angle of the WIDTH axis. 0.5-degree search over 90 degrees:
    exact enough for card bodies, and keeps the module numpy+PIL-only (CI has
    no cv2; the prototype used cv2.minAreaRect and this reproduces its boxes)."""
    px = xs.astype(np.float64)
    py = ys.astype(np.float64)
    best = None
    for step in range(180):                       # 0.0 .. 89.5 degrees
        th = step * (np.pi / 180.0) / 2.0         # 0.5 deg steps
        ct, st = np.cos(th), np.sin(th)
        u = px * ct + py * st
        v = -px * st + py * ct
        w = float(u.max() - u.min()) + 1.0
        h = float(v.max() - v.min()) + 1.0
        area = w * h
        if best is None or area < best[0]:
            best = (area, th, float(u.min()), float(u.max()), float(v.min()), float(v.max()))
    area, th, u0, u1, v0, v1 = best
    w = u1 - u0 + 1.0
    h = v1 - v0 + 1.0
    uc = (u0 + u1) / 2.0
    vc = (v0 + v1) / 2.0
    ct, st = np.cos(th), np.sin(th)
    cx = uc * ct - vc * st
    cy = uc * st + vc * ct
    if w < h:
        w, h = h, w
        th += np.pi / 2.0
    return cx, cy, w, h, th


def card_rects(a: np.ndarray, verbose: bool = False) -> list[tuple[float, float, float, float, float]]:
    """[(cx, cy, w, h, ang)] one rectangle per detected card, left to right."""
    strict = a >= STRICT
    rects = []
    for comp in _components(strict):
        if comp["area"] < MIN_AREA:
            continue
        x0, x1, y0, y1 = comp["x0"], comp["x1"], comp["y0"], comp["y1"]
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bw < MIN_W or bh < MIN_H:
            continue
        win_dark = a[y0:y1 + 1, x0:x1 + 1] < DARK
        comp_mask = np.zeros_like(win_dark)
        comp_mask[comp["ys"] - y0, comp["xs"] - x0] = True
        ink_rows = np.where((win_dark & comp_mask).sum(axis=1) >= MIN_DARK_ROW)[0]
        band_h = float(ink_rows[-1] - ink_rows[0] + 1) if len(ink_rows) else float(bh)
        col_dark = win_dark.mean(axis=0)
        splits, j = [], 0
        while j < bw:
            if col_dark[j] >= SPLIT_DARK_FRAC:
                k = j
                while k + 1 < bw and col_dark[k + 1] >= SPLIT_DARK_FRAC:
                    k += 1
                if k - j + 1 >= 2:
                    run_h = max(_longest_run(win_dark[:, c]) for c in range(j, k + 1))
                    if run_h >= WEDGE_RUN * band_h:
                        splits.append((j + k) // 2)
                j = k
            j += 1
        bounds = [0] + splits + [bw]
        for s0, s1 in zip(bounds[:-1], bounds[1:]):
            if s1 - s0 < MIN_BLOCK_W:
                continue
            keep = (comp["xs"] - x0 >= s0) & (comp["xs"] - x0 < s1)
            if int(keep.sum()) < MIN_BLOCK_PX:
                continue
            if cv2 is not None:
                pts = np.column_stack([comp["xs"][keep], comp["ys"][keep]]).astype(np.float32)
                (cx, cy), (rw, rh), ang = cv2.minAreaRect(pts)
                if rw < rh:
                    rw, rh, ang = rh, rw, ang + 90.0
                ang = np.deg2rad(ang)
            else:
                cx, cy, rw, rh, ang = _min_area_rect(comp["xs"][keep], comp["ys"][keep])
            if rw < 26 or rh < 14:
                continue
            rects.append((float(cx), float(cy), float(rw), float(rh), float(ang)))
    # single giant block == the whole sheet (an easy image): not a card sheet
    if len(rects) == 1:
        cx, cy, w, h, ang = rects[0]
        if w * h >= SINGLE_BLOCK_COVER * a.shape[0] * a.shape[1]:
            rects = []
    rects.sort(key=lambda r: r[0])
    if verbose:
        print(f"    [cards] {len(rects)}")
    return rects


# ---------------------------------------------------------------- geometry

def _corners(cx, cy, w, h, ang):
    ux, uy = np.cos(ang), np.sin(ang)
    vx, vy = -uy, ux
    hw, hh = w / 2.0, h / 2.0
    return [(cx - ux * hw - vx * hh, cy - uy * hw - vy * hh),
            (cx + ux * hw - vx * hh, cy + uy * hw - vy * hh),
            (cx + ux * hw + vx * hh, cy + uy * hw + vy * hh),
            (cx - ux * hw + vx * hh, cy - uy * hw + vy * hh)]


def _canonical_quad(rect):
    """tl/tr/br/bl by sum/difference, long side horizontal - the S14 recipe.
    No orientation trial: scores do not rank 0 deg vs 180 deg reliably."""
    corners = _corners(*rect)
    s = [x + y for x, y in corners]
    d = [y - x for x, y in corners]
    tl = corners[int(np.argmin(s))]
    br = corners[int(np.argmax(s))]
    tr = corners[int(np.argmin(d))]
    bl = corners[int(np.argmax(d))]
    def dist(p, q):
        return float(np.hypot(p[0] - q[0], p[1] - q[1]))
    w = (dist(tr, tl) + dist(br, bl)) / 2.0
    h = (dist(bl, tl) + dist(br, tr)) / 2.0
    if h > w:
        tl, tr, br, bl = bl, tl, tr, br
        w, h = h, w
    return tl, tr, br, bl, w, h


def rectify(img: Image.Image, rect) -> Image.Image:
    """Affine straightening. A card IS a rotated rectangle, so the map from its
    quad to an axis-aligned box is affine - no perspective needed. (PIL's QUAD
    path measured noticeably softer than this on the official set: 0.6 vs 0.75
    mean char, same rects, same reader.)"""
    tl, tr, br, bl, w, h = _canonical_quad(rect)
    W = max(8, int(round(w)))
    H = max(8, int(round(h)))
    if cv2 is not None:
        src = np.array([tl, tr, br, bl], np.float32)
        dst = np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32)
        M = cv2.getPerspectiveTransform(src, dst)
        return Image.fromarray(cv2.warpPerspective(
            np.array(img, dtype=np.uint8), M, (W, H), flags=cv2.INTER_CUBIC))
    a = (tr[0] - tl[0]) / W
    b = (bl[0] - tl[0]) / H
    c = tl[0]
    d = (tr[1] - tl[1]) / W
    e = (bl[1] - tl[1]) / H
    f = tl[1]
    return img.transform((W, H), Image.AFFINE, (a, b, c, d, e, f),
                         resample=Image.BICUBIC)


def ink_trim(a: np.ndarray) -> np.ndarray:
    ys, xs = np.where(a < 80)
    if len(ys) < 40:
        return a
    return a[max(0, int(ys.min()) - 3):int(ys.max()) + 4,
             max(0, int(xs.min()) - 3):int(xs.max()) + 4]


def strip_trim(a: np.ndarray, th: float = 0.6) -> np.ndarray:
    for _ in range(12):
        if a.shape[0] < 12 or a.shape[1] < 16:
            break
        cut = False
        row_dark = (a < DARK).mean(axis=1)
        col_dark = (a < DARK).mean(axis=0)
        if row_dark[0] > th:
            a = a[1:]
            cut = True
        if row_dark[-1] > th:
            a = a[:-1]
            cut = True
        if col_dark[0] > th:
            a = a[:, 1:]
            cut = True
        if col_dark[-1] > th:
            a = a[:, :-1]
            cut = True
        if not cut:
            break
    return ink_trim(a)


def edge_prune(a: np.ndarray) -> np.ndarray:
    comps = _components(a < DARK)
    big = [c["area"] for c in comps if c["area"] >= 25]
    if not big:
        return a
    band = float(np.median([c["y1"] - c["y0"] + 1 for c in comps if c["area"] >= 25]))
    out = a.copy()
    width = a.shape[1]
    edge_value = int(np.percentile(a, 90))
    for c in comps:
        if c["area"] < 15:
            continue
        if not (c["x0"] <= 3 or c["x1"] >= width - 4):
            continue
        ch = c["y1"] - c["y0"] + 1
        cw = c["x1"] - c["x0"] + 1
        if ch >= 1.15 * band or (cw <= 6 and ch >= 8):
            out[c["ys"], c["xs"]] = edge_value
    return out


# ---------------------------------------------------------------- seam split

SEAM_MIN_TOP = 8        # leading bright rows a seam column must have
SEAM_MIN_BOTTOM = 5      # dark rows it must carry down to the bottom edge
SEAM_MIN_H, SEAM_MIN_W = 44, 140   # the merged-card shape gate (measured)


def _seam_parts(a: np.ndarray, x: int) -> tuple[int, int, bool]:
    """(leading bright rows, trailing dark rows, do the runs meet cleanly)."""
    col = a[:, x]
    n = len(col)
    i = 0
    while i < n and col[i] >= 190:            # bright above (contiguous from row 0)
        i += 1
    j = n
    while j > 0 and col[j - 1] < 120:         # dark below (contiguous to the bottom)
        j -= 1
    return i, n - j, i <= j


def split_merged(a: np.ndarray, verbose: bool = False) -> list[np.ndarray]:
    """One rectified patch -> [patch] or [left, right] when a stagger seam is clear.

    A merged pair of staggered cards shows a column that is bright for a deep
    stretch from the top (both cards' margins above the seam) and then dark all
    the way down to the bottom edge (the wedge). A letter stem shows the same
    shape but with only the few margin rows above it - the depth gates
    (SEAM_MIN_TOP / SEAM_MIN_BOTTOM) are what tell the two apart; measured
    against the earlier attempts that split 'rivet' into 's r1lld' + 'Iet'."""
    h, w = a.shape
    if h < SEAM_MIN_H or w < SEAM_MIN_W:
        return [a]
    margin = max(12, int(0.08 * w))
    best = None
    for x in range(margin, w - margin):
        top, bottom, clean = _seam_parts(a, x)
        if not clean or top < SEAM_MIN_TOP or bottom < SEAM_MIN_BOTTOM:
            continue
        quality = 2 * min(top, 20) + 2 * min(bottom, 20)
        if best is None or quality > best[0]:
            best = (quality, x, top, bottom)
    if best is None:
        return [a]
    _, x, top, bottom = best
    left, right = a[:, :x], a[:, x:]
    if left.shape[1] < 24 or right.shape[1] < 20:
        return [a]
    if verbose:
        print(f"      seam at x={x} (top {top} bright, bottom {bottom} dark) -> "
              f"split {left.shape[1]}|{right.shape[1]}")
    return [left, right]


# ---------------------------------------------------------------- the route

def read_collage(img: Image.Image, verbose: bool = False,
                 weights: str | None = None) -> str:
    """One collage sheet -> text (cards left to right). "" when no card found."""
    gray = img.convert("L")
    a = np.array(gray, dtype=np.uint8)
    words = []
    for rect in card_rects(a, verbose=verbose):
        patch = rectify(gray, rect)
        p = np.array(patch, dtype=np.uint8)
        if p.shape[0] < 10 or p.shape[1] < 16:
            continue
        p = ink_trim(p)
        p = strip_trim(p)
        if p.shape[0] < 10 or p.shape[1] < 16:
            continue
        # the split works on the un-cooked patch: the furniture below is applied
        # once, per half. (Applying it twice - once here, once after the split -
        # measured 0.57 instead of 0.75: the second round eats real glyphs.)
        for half in split_merged(p, verbose=verbose):
            q = strip_trim(half)
            if q.shape[0] < 10 or q.shape[1] < 16:
                continue
            q = edge_prune(q)
            q = q[INSET:-INSET, INSET:-INSET] if (q.shape[0] > 2 * INSET and q.shape[1] > 2 * INSET) else q
            if q.shape[0] < 10 or q.shape[1] < 16:
                continue
            big = np.array(Image.fromarray(q).resize(
                (q.shape[1] * SCALE, q.shape[0] * SCALE), Image.LANCZOS), dtype=np.uint8)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
                Image.fromarray(big).save(fh.name)
                path = fh.name
            text = CR.read_image(path, weights or CR.DEFAULT_WEIGHTS)
            text = (text or "").strip()
            if verbose:
                print(f"    card@x{rect[0]:.0f} {q.shape[1]}x{q.shape[0]} -> {text!r}")
            if text:
                words.append(text)
    return " ".join(words)


def char_acc(got: str, want: str) -> float:
    import difflib
    sm = difflib.SequenceMatcher(None, got, want)
    return sum(b.size for b in sm.get_matching_blocks()) / max(1, len(want))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--image", required=True)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--weights", default=None)
    args = ap.parse_args(argv)
    with Image.open(args.image) as img:
        print(read_collage(img, verbose=args.verbose, weights=args.weights))
    return 0


if __name__ == "__main__":
    sys.exit(main())
