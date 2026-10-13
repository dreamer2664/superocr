#!/usr/bin/env python3
"""s26_digit_corrosion_probe.py — v3 digit identity under corrosion-grade noise.

S24 addendum 4 measured glyphcnn-v3 at 98.4% on digits from REAL crops, but
named the gap: digit-digit confusions on corrosion-grade noise were unmeasured
because the classic front end cannot align corrosion items (0/8 reads). The
iris corrosion residuals are exactly this population (003->802, 06->98).

Method (oracle-box, CNN-identity-only — segmentation is out of scope, that is
S25/barry's lane):
  1. Clone fam_corrosion's recipe from generator.py (heavy 6-offset stroke,
     140-260 pits placed on ink pixels, patch = paper bg, MedianFilter(3)),
     using the generator's own _paper/_ink_color/_bg_color/load_font helpers
     and seeded rng. We render our own digit strings and record exact
     per-character boxes at draw time (PIL prefix-width advance; the recipe
     has no rotation).
  2. Two arms, identical rng stream per string (same font, size, position):
       corroded  — pits on (n_pits = rng.randint(140, 260), as generator)
       control   — pits off (n_pits = 0); MedianFilter still applied
     The pits are the only difference between arms.
  3. Pieces: the reader's own mask front end (autocontrast gray ->
     baseline._family_mask with otsu fallback -> despeck -> trim), then crop
     at the oracle boxes. Minimum-size skips counted honestly.
  4. Score PieceCNN(glyphcnn-v3).opinions(pieces) against the true chars.
     Measure: identity accuracy (digits), digit->digit confusion matrix,
     0->O boundary, and confidence separation at errors (addendum-6
     discipline: does the prob gate separate right from wrong HERE?).

Receipts: reports/s26-digit-corrosion/probe-v1.{json,txt}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))

import baseline as B  # noqa: E402
import generator as G  # noqa: E402
import reader as R  # noqa: E402
from piece_cnn import PieceCNN  # noqa: E402

W, H = 640, 180  # hard-suite corrosion canvas size (checked on corrosion-0002.png)
DIGITS = "0123456789"


def render(seed: int, text: str, pits: bool):
    """Clone of fam_corrosion with a chosen text and recorded char boxes."""
    rng = random.Random(seed)
    base = G._paper(rng, W, H)
    size = rng.randint(26, 40)
    font = G.load_font(rng, size)
    d = ImageDraw.Draw(base)
    bb = d.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if tw > W - 16:
        size = max(12, size * (W - 16) // tw)
        font = G.load_font(rng, size)
        bb = d.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (W - tw) // 2 - bb[0]
    y = (H - th) // 2 - bb[1]
    ink = G._ink_color(rng)
    for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1)):
        d.text((x + ox, y + oy), text, font=font, fill=ink)

    # per-char TIGHT INK boxes: char i is placed at x + textlength(text[:i])
    # (PIL basic layout, no kerning, no rotation in this recipe); textbbox of
    # the single char at that origin gives its ink extent. Advance-wide boxes
    # were tried first and overlap neighbours (mono advance < ink width with
    # the heavy stroke), contaminating crops — tight boxes fix that.
    boxes = []
    for i, ch in enumerate(text):
        adv = x + d.textlength(text[:i], font=font)
        cb = d.textbbox((adv, y), ch, font=font)
        boxes.append((int(cb[0]) - 1, int(cb[2]) + 1, int(cb[1]) - 1, int(cb[3]) + 1))

    a = np.array(base, dtype=np.uint8).copy()
    if pits:
        g = G.rng_np(rng)
        n_pits = rng.randint(140, 260)
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
    img = Image.fromarray(a, "RGB").filter(ImageFilter.MedianFilter(3))
    fname = getattr(font, "path", "default").split("/")[-1]
    return img, boxes, fname


def mask_for(img: Image.Image) -> np.ndarray:
    """The reader's own front-end mask (same as s24_realcrop_probe)."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = B._family_mask(img, a, None)
    if mask is None:
        lv = B._otsu_level(a)
        mask = a < (lv * 0.85 if 128 <= lv <= 150 else lv)
        if mask.mean() > 0.5:
            mask = ~mask
    return R.trim(R.despeck(mask))


def run_arm(net: PieceCNN, items, base_seed: int, pits: bool):
    conf = {}
    probs_ok, probs_bad = [], []
    n = correct = skipped = 0
    letter_ok = 0
    by_font = {}
    for si, (text, scored) in enumerate(items):
        img, boxes, fname = render(base_seed + si, text, pits)
        fstat = by_font.setdefault(fname, [0, 0])
        mask = mask_for(img)
        # mask is trimmed; recover the offset of the trim
        gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
        a = np.array(gray, dtype=np.float32)
        full = B._family_mask(img, a, None)
        if full is None:
            lv = B._otsu_level(a)
            full = a < (lv * 0.85 if 128 <= lv <= 150 else lv)
            if full.mean() > 0.5:
                full = ~full
        full = R.despeck(full)
        # find trim offset: rows/cols kept by R.trim
        rows = np.where(full.any(axis=1))[0]
        cols = np.where(full.any(axis=0))[0]
        dy, dx = (int(rows[0]), int(cols[0])) if len(rows) and len(cols) else (0, 0)
        scored_idx = {i for i, _ in scored}
        pieces, chars = [], []
        for ci, ((x0, x1, y0, y1), ch) in enumerate(zip(boxes, text)):
            if ci not in scored_idx:
                continue
            gy0 = max(0, y0 - dy)
            gy1 = min(mask.shape[0], y1 - dy)
            gx0 = max(0, x0 - dx)
            gx1 = min(mask.shape[1], x1 - dx)
            if gy1 <= gy0 or gx1 <= gx0:
                skipped += 1
                continue
            piece = R.trim(mask[gy0:gy1, gx0:gx1])
            if piece.shape[0] < 6 or piece.sum() < 10:
                skipped += 1
                continue
            pieces.append(piece)
            chars.append(ch)
        if not pieces:
            continue
        ops = net.opinions(pieces)
        for (pred, p), ch in zip(ops, chars):
            n += 1
            ok = pred == ch
            correct += ok
            fstat[0] += 1
            fstat[1] += ok
            letter_ok += pred.lower() == ch.lower()
            (probs_ok if ok else probs_bad).append(p)
            if not ok:
                conf[f"{ch}->{pred}"] = conf.get(f"{ch}->{pred}", 0) + 1
    return {
        "n": n, "correct": correct, "skipped": skipped,
        "acc": round(correct / n, 4) if n else None,
        "letter_acc": round(letter_ok / n, 4) if n else None,
        "confusions": dict(sorted(conf.items(), key=lambda kv: -kv[1])),
        "prob_ok_mean": round(float(np.mean(probs_ok)), 4) if probs_ok else None,
        "prob_bad_mean": round(float(np.mean(probs_bad)), 4) if probs_bad else None,
        "prob_bad_ge9": sum(1 for p in probs_bad if p >= 0.9),
        "prob_bad_lt9": sum(1 for p in probs_bad if p < 0.9),
        "prob_ok_ge9": sum(1 for p in probs_ok if p >= 0.9),
        "prob_ok_lt9": sum(1 for p in probs_ok if p < 0.9),
        "by_font": {k: {"n": v[0], "correct": v[1],
                        "acc": round(v[1] / v[0], 4) if v[0] else None}
                    for k, v in sorted(by_font.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="models/glyphcnn-v3.npz")
    ap.add_argument("--n-digit", type=int, default=300)
    ap.add_argument("--n-mixed", type=int, default=100)
    ap.add_argument("--seed", type=int, default=26000)
    ap.add_argument("--out", default="reports/s26-digit-corrosion")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    # FIDELITY: real corrosion items are FULL labels (2-5 words + digit group
    # in ~40% of them) sharing the same 140-260 pits. Rendering only a short
    # digit string concentrates the full pit budget on 1/6th of the ink —
    # far more brutal than the real distribution (first smoke: 33/83 chars
    # destroyed). So: generate make_label-style full labels with a FORCED
    # digit group (shapes from the generator's _DIGIT_SHAPES), and score
    # only the digit-group characters.
    items = []  # (label, [(idx, char), ...])
    for _ in range(a.n_digit):
        n = rng.randint(2, 5)
        words = [G.case_word(rng, rng.choice(G._WORDS)) for _ in range(n)]
        shape = rng.choice(G._DIGIT_SHAPES)
        digits = shape % tuple(rng.randint(0, 9) for _ in range(shape.count("%")))
        pos = rng.randint(1, len(words))
        words.insert(pos, digits)
        label = " ".join(words)
        start = label.index(digits)
        items.append((label, [(start + i, c) for i, c in enumerate(digits)]))
    for _ in range(a.n_mixed):
        # 0/O boundary: digit group next to a word containing O
        n = rng.randint(2, 4)
        words = [G.case_word(rng, w) for w in
                 (rng.choice(G._WORDS) for _ in range(n))]
        digits = "".join(rng.choice("0O1Il9") for _ in range(rng.randint(2, 3)))
        pos = rng.randint(1, len(words))
        words.insert(pos, digits)
        label = " ".join(words)
        start = label.index(digits)
        score = [(start + i, c) for i, c in enumerate(digits) if c in DIGITS]
        items.append((label, score))

    net = PieceCNN(str(ROOT / a.weights))
    t0 = time.time()
    corroded = run_arm(net, items, a.seed + 100000, pits=True)
    control = run_arm(net, items, a.seed + 100000, pits=False)
    dt = time.time() - t0

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    whash = hashlib.sha256((ROOT / a.weights).read_bytes()).hexdigest()[:12]
    out = {
        "tool": "tools/s26_digit_corrosion_probe.py",
        "commit": sha, "weights": a.weights, "weights_sha256_12": whash,
        "seed": a.seed, "n_strings": len(items),
        "digit_strings": a.n_digit, "mixed_strings": a.n_mixed,
        "canvas": [W, H], "seconds": round(dt, 1),
        "arms": {"corroded": corroded, "control": control},
    }
    outdir = ROOT / a.out
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "probe-v1.json").write_text(json.dumps(out, indent=2) + "\n")

    lines = [
        "S26 — v3 digit identity under corrosion-grade noise (oracle boxes)",
        f"commit {sha} · weights {a.weights} sha256:{whash} · seed {a.seed} · "
        f"{len(items)} full labels ({a.n_digit} digit + {a.n_mixed} mixed), digits scored · {dt:.0f}s",
        "",
        f"{'arm':10s} {'n':>5s} {'acc':>7s} {'letter':>7s} {'skip':>5s} "
        f"{'P(ok)':>7s} {'P(bad)':>7s} bad>=.9 bad<.9",
    ]
    for name, arm in (("corroded", corroded), ("control", control)):
        lines.append(
            f"{name:10s} {arm['n']:5d} {arm['acc']:7.4f} {arm['letter_acc']:7.4f} "
            f"{arm['skipped']:5d} {arm['prob_ok_mean'] or 0:7.4f} "
            f"{arm['prob_bad_mean'] or 0:7.4f} {arm['prob_bad_ge9']:7d} "
            f"{arm['prob_bad_lt9']:6d}")
    for name, arm in (("corroded", corroded), ("control", control)):
        lines.append(f"\nper-font accuracy — {name}:")
        for k, v in arm["by_font"].items():
            lines.append(f"  {k:32s} {v['correct']}/{v['n']} = {v['acc']}")
    for name, arm in (("corroded", corroded), ("control", control)):
        lines.append(f"\ntop confusions — {name}:")
        for k, v in list(arm["confusions"].items())[:15]:
            lines.append(f"  {k}: {v}")
    txt = "\n".join(lines) + "\n"
    (outdir / "probe-v1.txt").write_text(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
