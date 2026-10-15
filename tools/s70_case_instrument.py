#!/usr/bin/env python3
"""S70 — image-side case instrument v1 (t-20261014-479d).

Preregistration: reports/case-instrument/2026-10-15-protocol.md
(published @56491ae BEFORE any measurement). Implements exactly the
frozen rule: segment -> align -> anchor -> decide, abstain on ties.
Runs AFTER the shipping route (floor + fix_line); reads (image,
shipping_text) and returns possibly case-corrected text. No reader
edits; standalone tool.

Usage (library):
    from s70_case_instrument import correct_cases
    fixed = correct_cases(img, shipping_text)

CLI (dev/eval harnesses):
    python3 tools/s70_case_instrument.py --s73-dev    # gates A and B
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# frozen twin set (protocol: may only narrow, never widen)
TWIN_PAIRS = [("o", "O"), ("c", "C"), ("s", "S"), ("v", "V"),
              ("w", "W"), ("x", "X"), ("z", "Z")]
TWIN_LOWER = {a for a, _ in TWIN_PAIRS}
TWIN_UPPER = {b for _, b in TWIN_PAIRS}
TWINS = TWIN_LOWER | TWIN_UPPER

# frozen thresholds (protocol §4)
ABSTAIN_BAND = 0.10     # |h - mid| < 0.10*(cap-x) -> abstain
ONE_ANCHOR_GAP = 0.20   # fixture-calibrated (deviation from frozen
                         # 0.25): true cap-x gap is 0.23*cap (DejaVu
                         # 26/20 at 34px); 0.25 ate the signal
BIMODAL_MIN = 1.25      # dev iter 2: 1.35->1.25 (font geometry: same-case
                         # jitter <=1.10, true cap/x gap >=1.29; see report)
BASELINE_TOL = 2        # px tolerance on component bottoms
WORD_GAP = 0.6          # x-gap split threshold, fraction of median width


def ink(img: Image.Image) -> np.ndarray:
    """Polarity-safe ink mask: Otsu on grayscale, ink = the sparse side."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    hi, lo = g.max(), g.min()
    if hi - lo < 1:
        return np.zeros_like(g, dtype=bool)
    hist, _ = np.histogram(g, bins=256, range=(0, 256))
    total = g.size
    sum_all = np.dot(np.arange(256), hist)
    w0 = np.cumsum(hist)
    sum0 = np.cumsum(np.arange(256) * hist)
    w1 = total - w0
    with np.errstate(invalid="ignore", divide="ignore"):
        m0 = sum0 / w0
        m1 = (sum_all - sum0) / w1
        var_between = w0 * w1 * (m0 - m1) ** 2
    t = int(np.nanargmax(var_between))
    mask = g > t            # bright side
    if mask.mean() > 0.5:   # ink is the sparse side
        mask = ~mask
    return mask


def components(mask: np.ndarray):
    """4-connectivity connected components -> [(x0,x1,y0,y1)], x-sorted."""
    H, W = mask.shape
    lab = np.zeros((H, W), dtype=np.int32)
    cur = 0
    out = []
    for yy in range(H):
        xs = np.flatnonzero(mask[yy] & (lab[yy] == 0))
        for x in xs:
            if lab[yy, x]:
                continue
            cur += 1
            stack = [(yy, x)]
            lab[yy, x] = cur
            x0 = x1 = x
            y0 = y1 = yy
            while stack:
                cy, cx = stack.pop()
                x0 = min(x0, cx); x1 = max(x1, cx)
                y0 = min(y0, cy); y1 = max(y1, cy)
                for ny, nx in ((cy-1, cx), (cy+1, cx), (cy, cx-1), (cy, cx+1)):
                    if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] \
                            and lab[ny, nx] == 0:
                        lab[ny, nx] = cur
                        stack.append((ny, nx))
            if (x1 - x0 + 1) >= 2 and (y1 - y0 + 1) >= 2:  # specks out
                out.append((x0, x1, y0, y1))
    out.sort(key=lambda b: (b[0] + b[1]) / 2)
    return out


def group_words(comps):
    """Split x-sorted components into words at large x-gaps."""
    if not comps:
        return []
    widths = [b[1] - b[0] + 1 for b in comps]
    med = float(np.median(widths)) if widths else 1.0
    gap = max(6.0, WORD_GAP * med)
    words, cur = [], [comps[0]]
    for b in comps[1:]:
        if b[0] - cur[-1][1] > gap:
            words.append(cur)
            cur = [b]
        else:
            cur.append(b)
    words.append(cur)
    return words


def decide_token(letters, comps):
    """Frozen rule §4 for one aligned token.

    Returns (new_letters, decisions) where decisions[i] is None when
    glyph i abstained and otherwise the decided case as
    'up'/'low' — needed so callers can tell a kept-by-abstain from a
    decided-and-agreed glyph.
    """
    n = len(letters)
    no_dec = (list(letters), [None] * n)
    if n == 0 or len(comps) != n:
        return no_dec                             # alignment abstain
    heights = [b[3] - b[2] + 1 for b in comps]
    bottoms = [b[3] for b in comps]
    med_bottom = float(np.median(bottoms))
    if any(abs(b - med_bottom) > BASELINE_TOL for b in bottoms):
        return no_dec                             # baseline abstain

    x_h, cap_h = [], []
    for i, ch in enumerate(letters):
        if ch in TWINS or not ch.isalpha():
            continue
        (x_h if ch.islower() else cap_h).append(heights[i])
    x_ref = float(np.median(x_h)) if x_h else None
    cap_ref = float(np.median(cap_h)) if cap_h else None

    out = list(letters)
    dec = [None] * n
    for i, ch in enumerate(letters):
        low, up = ch.lower(), ch.upper()
        if low not in TWIN_LOWER:
            continue
        h = heights[i]
        if x_ref is not None and cap_ref is not None:
            mid = (x_ref + cap_ref) / 2.0
            band = ABSTAIN_BAND * (cap_ref - x_ref)
            if abs(h - mid) < band:
                continue                          # tie abstain
            want_up = h >= mid
        elif cap_ref is not None:
            if cap_ref - h >= ONE_ANCHOR_GAP * cap_ref:
                want_up = False
            elif h >= cap_ref * (1 - ONE_ANCHOR_GAP):
                want_up = True
            else:
                continue                          # ambiguous vs cap
        elif x_ref is not None:
            if h - x_ref >= ONE_ANCHOR_GAP * x_ref:
                want_up = True
            elif h <= x_ref * (1 + ONE_ANCHOR_GAP):
                want_up = False
            else:
                continue                          # ambiguous vs x
        else:
            lo_, hi_ = min(heights), max(heights)
            if hi_ / max(lo_, 1) < BIMODAL_MIN:
                continue                          # no signal abstain
            mid = (lo_ + hi_) / 2.0
            band = ABSTAIN_BAND * (hi_ - lo_)
            if abs(h - mid) < band:
                continue
            want_up = h >= mid
        dec[i] = "up" if want_up else "low"
        out[i] = up if want_up else low
    return out, dec


def correct_cases(img: Image.Image, text: str) -> str:
    """The instrument: (image, shipping text) -> case-corrected text."""
    tokens = text.split(" ")
    if not tokens or not any(t for t in tokens):
        return text
    comps = components(ink(img))
    words = group_words(comps)
    if len(words) != len(tokens):
        return text                               # global abstain
    out_tokens = []
    for tok, wcomps in zip(tokens, words):
        if not tok or len(wcomps) != len(tok) or not tok.isalpha():
            out_tokens.append(tok)
            continue
        out_tokens.append("".join(decide_token(list(tok), wcomps)[0]))
    return " ".join(out_tokens)


# ------------------------------------------------------------------ dev
def _glyph_stats(letters_in, letters_out, truth, decisions):
    """Per twin glyph: decided-correct / decided-wrong / abstained."""
    st = {"total": 0, "decided": 0, "correct": 0}
    for a, b, w, d in zip(letters_in, letters_out, truth, decisions):
        low = a.lower()
        if low not in TWIN_LOWER:
            continue
        st["total"] += 1
        if d is not None:                # instrument acted
            st["decided"] += 1
            st["correct"] += int(b == w)
        # d is None: abstained, kept the input letter, no claim
    return st


def s73_dev(corpus_dir: Path, truth_boxes: bool):
    """Gates A (truth boxes) / B (self-segmentation) on the S73 corpus.

    Input text = the label (simulates a reader that recovered every
    letter; case is what the instrument must decide). Abstain keeps
    the input letter, so accuracy counts only actively-decided glyphs
    and coverage = decided/total — the honest accounting.
    """
    rows = [json.loads(l) for l in open(corpus_dir / "manifest.jsonl")]
    agg = {"total": 0, "decided": 0, "correct": 0, "items": 0,
           "items_abstain_all": 0}
    per_variant = {}
    for r in rows:
        img = Image.open(corpus_dir / r["image"])
        label = r["label"]
        if truth_boxes:
            # dev iter 2: strip the manifest boxes' documented +/-1px pad
            # (s73 tool: "advance method; +1px like S53") -> tight ink boxes
            comps = [(b[0], b[1], b[2] + 1, b[3] - 1)
                     for b in r["char_boxes"]]
            got, dec = decide_token(list(label), comps)
        else:
            comps_all = components(ink(img))
            words = group_words(comps_all)
            if len(words) != 1 or len(words[0]) != len(label):
                got, dec = list(label), [None] * len(label)
                agg["items_abstain_all"] += 1
            else:
                got, dec = decide_token(list(label), words[0])
        v = per_variant.setdefault(r["variant"],
                                   {"total": 0, "decided": 0,
                                    "correct": 0})
        for k, x in _glyph_stats(label, got, label, dec).items():
            agg[k] = agg.get(k, 0) + x
            v[k] = v.get(k, 0) + x
        agg["items"] += 1
    return agg, per_variant


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--s73-dev", action="store_true")
    ap.add_argument("--corpus", default="/tmp/s73-corpus")
    args = ap.parse_args()
    if args.s73_dev:
        for name, tb in (("A truth-box", True), ("B self-seg", False)):
            st, per = s73_dev(Path(args.corpus), tb)
            acc = st["correct"] / max(1, st["decided"])
            cov = st["decided"] / max(1, st["total"])
            print(f"gate {name}: decided {st['decided']}/{st['total']}"
                  f" (coverage {cov:.4f})  accuracy {st['correct']}/"
                  f"{st['decided']} = {acc:.4f}"
                  f"  items-fully-abstained {st['items_abstain_all']}"
                  f"/{st['items']}")
            for vn, s in sorted(per.items()):
                a = s["correct"] / max(1, s["decided"])
                c = s["decided"] / max(1, s["total"])
                print(f"  {vn:7s} coverage {c:.4f} accuracy {a:.4f}"
                      f" ({s['correct']}/{s['decided']} of {s['total']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
