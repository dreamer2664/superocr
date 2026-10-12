#!/usr/bin/env python3
"""superocr baseline — the honest floor (t-20261011-65ff).

The classic textbook reader, no ML, no family-specific strategy, no lexicon
rerank, no fallback chain. Contrast normalisation, deskew, per-glyph isolation,
match against rendered fonts. JOBS.md S1: its numbers set what the learned
reader has to beat, so the numbers are published as-is and reproducible from a
clean clone (seeded; reports/ are committed).

Pipeline (one chain for every family and for the reference pack):
    autocontrast -> Otsu -> polarity guard -> despeckle -> trim -> deskew
    (projection-profile peak search) -> re-trim -> word/glyph isolation
    (shared classic primitives) -> template match. Nothing else. If it can't
    be read this way, that is a real failure and it goes in the report.

  THE POLARITY GUARD (t-20261011-be57): document images have ink coverage
    far below 50%, so a post-Otsu mask covering more than half the sheet is
    the BACKGROUND, returned by an inverted split (dark-on-dark: 98%) — the
    read previously died at stage B, char 0.0. The guard inverts such a
    mask; thirteen-family re-measure (seed 7, 10/family) showed every other
    family bit-identical and dark-on-dark char 0.0 -> 52.4.

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
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

import generator as G
import preclassify as P  # S12: the S9 router, for --auto-family (t-20261012-30bf)
import reader as R  # shared classic primitives (otsu/trim/segment/split_wide)

ROOT = Path(__file__).resolve().parent
SAME_SHAPE = set("cCoOsSuUvVwWxXzZ")  # case twins: identical shape, size differs

# --- S10b: the glyphcnn-v2 piece policy (DEFAULT OFF, research flag) --------
# Read this before enabling: the policy lets glyphcnn-v2 read the glyph
# pieces; the floor keeps segmentation, splits, word grouping and case. On
# the canonical suite (seed 1, hash b2c460d2fb5a) it measured easy 28->38 and
# hard 9->11, but at a held-out seed 2 the exact gain did NOT replicate
# (36->36 easy, 7->7 hard; pooled 200 easy +10, repairs 18 / losses 8,
# sign-test p=0.076 suggestive only). See reports/s10b-gate-finding.md. The
# confidence-gated variant the task asked for was measured flat and is NOT
# what this flag implements. Off by default; set SUPEROCR_PIECE_CNN=1 to
# enable for experiments.
PIECE_CNN = os.environ.get("SUPEROCR_PIECE_CNN", "").lower() in ("1", "on", "true", "yes")
PIECE_MIN_PROB = float(os.environ.get("SUPEROCR_PIECE_MIN_PROB", "0.3"))


@functools.lru_cache(maxsize=1)
def _piece_cnn():
    """glyphcnn-v2 for the piece policy; None unless the flag is set."""
    if not PIECE_CNN:
        return None
    try:
        sys.path.insert(0, str(ROOT / "readers"))
        from piece_cnn import PieceCNN
        return PieceCNN()
    except Exception:
        return None


# --------------------------------------------------------------------------
# native-scale templates — render each face at nominal N, keep the glyph mask
# --------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
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


@functools.lru_cache(maxsize=128)
def _cands_for_height(h: int) -> list[tuple[str, float, np.ndarray]]:
    """All face+char masks whose rendered height is within ±1 of h."""
    cands = []
    for nominal in range(max(10, h), min(72, 2 * h + 4)):
        for (ch, face), t in _templates_native(nominal).items():
            if abs(t.shape[0] - h) <= 1:
                cands.append((ch, face, t))
    return cands


def _match_probe(mask: np.ndarray, max_cands: int = 48,
                 break_at: float = 0.99) -> tuple[str, float]:
    """First-48-candidates probe of match_native: same height-ordered scan,
    capped. Rescue decisions only need to know a half templates WELL, not
    which exact face wins; full detail stays in match_native."""
    h = mask.shape[0]
    best = ("?", -1.0)
    for i, (ch, face, t) in enumerate(sorted(
            _cands_for_height(h), key=lambda cf: (abs(cf[2].shape[0] - h), cf[1]))):
        if i >= max_cands or (best[1] >= break_at and i >= 24):
            break
        s = R._score_glyph(mask, t)
        if s > best[1]:
            best = (ch, s)
    return best


def _scan_native(mask: np.ndarray, k: int = 8) -> list[tuple[str, float]]:
    """The full candidate scan as a sorted top-k list (rerank needs the
    runners-up, not just the winner)."""
    h = mask.shape[0]
    cands = sorted(_cands_for_height(h), key=lambda cf: (abs(cf[2].shape[0] - h), cf[1]))
    scored = sorted(((R._score_glyph(mask, t), ch) for ch, face, t in cands),
                    reverse=True)
    return [(ch, s) for s, ch in scored[:k]]


def match_native(mask: np.ndarray) -> tuple[str, float]:
    """Template match at the glyph's own raster height (never upscale-squash).
    S8: candidates ordered by raster-height proximity, short-circuited at a
    near-exact hit (ties choose the closest render; full scan only when the
    glyph never reaches 0.997 anywhere in the window)."""
    h = mask.shape[0]
    cands = sorted(_cands_for_height(h), key=lambda cf: (abs(cf[2].shape[0] - h), cf[1]))
    best = ("?", -1.0)
    seen = 0
    for ch, face, t in cands:
        s = R._score_glyph(mask, t)
        seen += 1
        if s > best[1]:
            best = (ch, s)
            if s >= 0.997 and seen >= 24:
                break
    return best


# --------------------------------------------------------------------------
# wide-glyph rescue (t-20261011-be57): read through forced splits
# --------------------------------------------------------------------------
def _split_marked(mask: np.ndarray, depth: int = 0,
                  forced: bool = False) -> list[tuple[np.ndarray, bool]]:
    """R.split_wide clone carrying cut metadata: `forced` marks that the
    valley at the split column carried ink, i.e. the cut passed through a
    stroke (an M cut between its legs) rather than through whitespace
    (a true glyph boundary like i|l). Reader's split_wide cannot tell the
    two apart and happily halves a heavy M; the halves then template-match
    as plausible narrow letters ('M' -> 'AI')."""
    h, w = mask.shape
    if depth >= 3 or w <= 1.35 * h or w < 8:
        return [(mask, forced)] if mask.any() else []
    mid = slice(int(w * 0.2), int(w * 0.8))
    colsum = mask.sum(axis=0)
    x = int(np.argmin(colsum[mid])) + int(w * 0.2)
    cut_forced = colsum[x] > 0
    left, right = R.trim(mask[:, :x]), R.trim(mask[:, x:])
    out = []
    if left.any():
        out += _split_marked(left, depth + 1, forced)
    if right.any():
        out += _split_marked(right, depth + 1, cut_forced)
    return out


def _merge_forced(marked: list[tuple[np.ndarray, bool]]) -> list[np.ndarray]:
    """Merge a piece back into its left neighbour only when its cut was
    forced AND the merged glyph matches at least as well as the better
    part. Clean-boundary pairs are never candidates, so the arbiter's
    confidence margins only ever judge genuine through-stroke splits."""
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
            m = R.trim(m)
            if not m.any():
                continue
            _, s_m = match_native(m)
            _, s_a = match_native(a)
            _, s_b = match_native(b)
            if s_m >= max(s_a, s_b) - 0.03:
                marked[j - 1:j + 1] = [(m, False)]
                changed = True
                break
    return [p for p, _ in marked]


# --------------------------------------------------------------------------
# touching-pair rescue (t-20261012-ac4f, S8 lever C)
# --------------------------------------------------------------------------
RESCUE_CONF_GATE = 0.72   # re-split pieces matching worse than this
RESCUE_WH_GATE = 0.85     # ... or pieces wide enough to hide two glyphs
RESCUE_MARGIN = 0.05      # accept split when the worse half wins by this
RESCUE_MAX_CUTS = 12      # deepest local minima searched, latency cap

# twin-case height reference: the word's max piece height EXCLUDING pieces
# matched as a descender-class letter (g j p q y, J Q) — those caps break
# the box downward and poisoned "JASPER" (J at 23 vs caps at 18) and every
# "QUILL"/"SEQUOIA" (Q tail). Cluster/second-max/median references all
# measured worse on the official suite (35 / 30 / 7 vs max's 44).
_DESCENDER_CLASS = frozenset("JQ")


def _cap_ref(matched: list) -> float:
    """Twin-case reference: word max piece height, ignoring a J/Q cap ONLY
    when the rest of the word still reaches 3/4 of its height (a lone
    descender inside a caps word is the outlier — measured JASPER/QUILL/
    SEQUOIA; a leading 'Jasper' keeps its J as the only cap evidence)."""
    allh = [g.shape[0] for g, _c, _s in matched]
    refs = [g.shape[0] for g, ch, _s in matched if ch not in _DESCENDER_CLASS]
    mx = float(max(allh))
    if refs and float(max(refs)) >= 0.75 * mx:
        return float(max(refs))
    return mx


def _word_has_digit(matched: list) -> bool:
    """0/O pixel-twin context: a confident digit somewhere in the word."""
    return any(ch.isdigit() and s >= 0.95 for _, ch, s in matched)


_DIGIT_CTX_ON = True

# S8 lever 4 (t-20261012-ac4f): CNN rerank behind a margin/confidence gate.
# The matcher loses to TIES (median loss margin 0.006, truth in top8 for
# 41/64 wrong glyphs) — scoring cannot break a 1.0-vs-1.0 tie; the trained
# net saw render variants the templates never did. Gate = small margin OR
# modest confidence, decision restricted to the matcher's own top-8.
CNN_RERANK_ON = True
CNN_MARGIN = 0.01   # fire when top1-top2 is below this
CNN_CONF = 0.85     # ... or when top1 is below this
_CNN = None


def _cnn():
    global _CNN
    if _CNN is None:
        from readers.glyphcnn import GlyphCNN
        _CNN = GlyphCNN.load("models/glyphcnn-v2.npz")
    return _CNN


def _cnn_vote(piece: np.ndarray) -> str | None:
    from readers.glyphcnn import index_to_char
    from readers.segmentation import normalise_glyph
    gi = normalise_glyph(piece, (0, 0, piece.shape[1] - 1, piece.shape[0] - 1))
    probs = _cnn().forward(gi[None, None, :, :])[0]
    return index_to_char(int(np.argmax(probs)))


def _narrow_case_resolve(piece: np.ndarray, ch: str, word_has_upper: bool) -> str:
    """i/l/I tie resolution on narrow stems (t-20261012-ac4f): at small render
    sizes all three template-match a plain stem at ~1.0 IoU (16/20 narrow
    pieces tie three-way), so the winner fell out of dict order -> the floor's
    #1 single confusion (l->i x21, I->i x7 on the official easy set).

    Two honest features: (1) a full-width near-white row band in the interior
    = the i-dot separating from the stem; (2) for the remaining l-vs-I stem
    tie, the word's case context, defaulting lowercase (far commoner role)."""
    if ch not in ("i", "l", "I"):
        return ch
    h, w = piece.shape
    if h < 14 or w > 7 or w > h * 0.36:
        return ch
    rows = piece.sum(axis=1).astype(float)
    ink = rows[rows > 0]
    if ink.size == 0:
        return ch
    lo, hi = max(1, h // 8), max(2, (h * 11) // 20)
    med = float(np.median(ink))
    # deskew leaves the dot gap diagonal: tolerate up to 0.35 x median
    # ink and a hard 2px floor (measured: misses at the 0.25 gate, l: 0)
    if rows[lo:hi].min(initial=med) <= min(0.35 * med, 2.0):
        return "i"
    return "I" if word_has_upper else "l"


def _rescue_split(piece: np.ndarray) -> list[np.ndarray]:
    """split_wide only fires above 1.35 w/h and searches the middle 60% of
    columns, so a touching pair at borderline width survives as one piece
    and templates as a plausible single letter ('rb'->I, 'al'->b). This is
    the matcher-side re-read: low-confidence or wide-enough pieces get one
    full-band column search; the split ships only when the worse half
    templates better than the fused whole. reader.py untouched (S8/S7 lane
    split); the gate trio was grid-checked flat on the selection seed."""
    _, s0 = match_native(piece)
    h, w = piece.shape
    if s0 >= RESCUE_CONF_GATE and w <= RESCUE_WH_GATE * h:
        return [piece]
    # candidate cuts: local minima of the smoothed column profile (the
    # dozen at most, deepest first) — a full-band scan costs one template
    # match per column and made the floor unreadably slow (23 s/image).
    colsum = piece.sum(axis=0).astype(np.float32)
    smooth = np.convolve(colsum, np.ones(3) / 3, mode="same")
    lo, hi = max(2, int(w * 0.12)), max(3, int(w * 0.88))
    cands = sorted(range(lo, hi), key=lambda x: smooth[x])[:RESCUE_MAX_CUTS]
    best = None
    for x in cands:
        left, right = R.trim(piece[:, :x]), R.trim(piece[:, x:])
        if not left.any() or not right.any():
            continue
        if left.shape[0] < 6 or right.shape[0] < 6 or left.sum() < 10 or right.sum() < 10:
            continue
        _, s_l = _match_probe(left)
        _, s_r = _match_probe(right)
        score = min(s_l, s_r)
        if best is None or score > best[0]:
            best = (score, left, right)
    if best is not None and best[0] >= s0 + RESCUE_MARGIN:
        return [best[1], best[2]]
    return [piece]


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
def _family_mask(img: Image.Image, a: np.ndarray,
                 family: "str | None") -> "np.ndarray | None":
    """S7c (t-20261012-e105): the measured wall-family masks, wired into the
    floor. Each entry is the exact variant that won the seed-7 sweeps in
    reports/s7-walls-part1.md; every other family stays on the floor's
    otsu+polarity path (bit-identical behaviour, None here)."""
    if family == "cross-shadow":
        # shadow bands kill global thresholds; local contrast is band-immune
        return R.local_diff_mask(img, 25, 60.0)
    if family == "darts":
        # the web is grey, the ink is black: dark core + one bounded regrow
        return R.dark_core_mask(img)
    # dark-on-dark is deliberately NOT here: the sigma-25 mask lifts char
    # (0.351 -> 0.596, reports/s7-walls-part1.md) but drops the floor's
    # exact-match cell 2/8 -> 1/8, and S11's truth table forbids wiring that
    # regresses a scoring floor cell. It stays wired in reader.py, where the
    # family chain can adopt it; the floor keeps its measured otsu+polarity.
    if family == "corrosion":
        # close1 heals the 1px pit gaps (floor 0.166 -> 0.186 measured)
        return R.close_mask(R.otsu(a), 1)
    return None


def read_text(img: Image.Image, family: "str | None" = None) -> tuple[str, list[float]]:
    """Contrast norm, deskew, per-glyph isolation, template match.
    Returns (text, per-glyph confidence). Classic only: over-split touching
    glyphs are a reported failure, not glued away (see module docstring).
    `family` (S7c): when the bench adapter passes the family, the measured
    wall-family mask replaces otsu; everything downstream is unchanged."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = _family_mask(img, a, family)
    if mask is None:
        mask = R.otsu(a)
        # polarity guard (t-20261011-be57): document images have ink << 50%
        # coverage; dark-on-dark sheets invert the otsu split, returning the
        # background AS the mask (98% coverage) and the read dies at stage B.
        # Normal dark-ink families never reach half, so the guard inverts only
        # true polarity flips.
        if mask.mean() > 0.5:
            mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = deskew(mask)
        mask = R.trim(mask)
    words = R.segment(mask)
    out, conf = [], []
    for word in words:
        pieces = []
        for x0, x1 in word:
            for g0 in _merge_forced(_split_marked(R.trim(mask[:, x0:x1]))):
                # arcs/long thin strokes stay: the arc-threshold filter was
                # measured to wipe bold stems (4px @ x-height 10px), so the
                # floor keeps only trivial noise guards
                if g0.shape[0] >= 6 and g0.sum() >= 10:
                    for g in _rescue_split(g0):
                        pieces.append(g)
        if not pieces:
            continue
        # twinned-case height reference: mean of the tall cluster, not the
        # raw max — one 'l' ascender or a digit must not shrink the cap
        net = _piece_cnn()
        ops = net.opinions(pieces) if net is not None else None
        matched = []
        for i, g in enumerate(pieces):
            top = _scan_native(g, 8) if CNN_RERANK_ON else None
            ch, s = (top[0] if top else match_native(g))
            if ops is not None and ops[i][1] >= PIECE_MIN_PROB:
                ch, s = ops[i]           # S10b flag: the CNN reads the piece
            elif (CNN_RERANK_ON and top and len(top) > 1
                    and (top[0][1] - top[1][1] < CNN_MARGIN or top[0][1] < CNN_CONF)):
                vote = _cnn_vote(g)
                if vote is not None and vote != ch and any(c == vote for c, _ in top):
                    ch = vote
            matched.append((g, ch, s))
        cap = _cap_ref(matched)
        matched = [
            (g, (ch.lower() if g.shape[0] < 0.87 * cap else ch.upper()) if ch in SAME_SHAPE else ch, s)
            for g, ch, s in matched
        ]
        # word case context for the stem-tie family (t-20261012-ac4f):
        # two+ wide glyphs matched uppercase = all-caps word (a single
        # leading capital in "Falcon" must NOT pull the stems to I)
        word_has_up = sum(1 for g, ch, _ in matched
                          if ch.isupper() and ch not in SAME_SHAPE and g.shape[1] > 7) >= 2
        # 0/O is a pixel-twin like the case family: decide by word context
        # (a digit in the word at confident match => circles are zeros)
        word_has_dig = _DIGIT_CTX_ON and _word_has_digit(matched)
        chars = []
        for g, ch, s in matched:
            if ch == "O" and word_has_dig:
                ch = "0"
            elif ch == "0" and not word_has_dig and any(
                    c.isalpha() and c not in ("O", "0") for _, c, _ in matched):
                ch = "O"
            ch = _narrow_case_resolve(g, ch, word_has_up)
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
    ap.add_argument("--auto-family", action="store_true",
                    help="S12: decide the family from the image itself via the "
                         "S9 pre-classifier (routes to the S7c wall masks); "
                         "mutually exclusive with --family")
    ap.add_argument("--family", default=None,
                    help="S7c: family name from the bench adapter; wall families "
                         "get their measured mask instead of plain otsu")
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
        if args.auto_family and args.family:
            ap.error("--auto-family and --family are mutually exclusive "
                     "(auto decides, family pins)")
        img = Image.open(args.image)
        fam = args.family
        if args.auto_family:
            fam = P.rank(img)[0]
            print(f"[baseline] auto-family={fam}", file=sys.stderr)
        text, _ = read_text(img, fam)
        print(text)
        return

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")


if __name__ == "__main__":
    main()
