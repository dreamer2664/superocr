#!/usr/bin/env python3
"""S24 probe 2 (t-20261012-c4af, marcus): case discrimination on REAL suite crops.

The synthetic-crop probe (tools/s24_case_probe.py) says glyphcnn-v3 decides
24/26 case pairs at >=80%. This measures the same question on crops cut from
actual suite images by the actual classic segmentation — the honest next step
named in the S24 report.

Method (no alignment guessing):
  1. run the floor reader's own pipeline to per-glyph pieces (baseline.py
     internals, plain route) on every suite item;
  2. keep items whose read is EXACT — there, pieces align 1:1 with the
     label's non-space characters by construction;
  3. score PieceCNN(weights).opinions(pieces) against the true characters.

Reports: identity accuracy, and the decision metric for the S24 proposal —
P(case correct | letter correct), overall and on case-twin-ambiguous letters.

Run:  python3 tools/s24_realcrop_probe.py [--suite-dir SUITES]
        [--weights models/glyphcnn-v3.npz] [--limit 0]
Deterministic, offline; ~1-2 min for both suites on a small box.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))

import baseline as B  # noqa: E402
import reader as R  # noqa: E402  (baseline's primitive module: otsu/trim/segment)
from piece_cnn import PieceCNN  # noqa: E402


def pieces_for(img: Image.Image) -> list[np.ndarray]:
    """Replicate read_text's front end up to per-glyph pieces (plain route)."""
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = B._family_mask(img, a, None)
    if mask is None:
        lv = B._otsu_level(a)
        mask = a < (lv * 0.85 if 128 <= lv <= 150 else lv)
        if mask.mean() > 0.5:
            mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    out = []
    for word in R.segment(mask):
        for x0, x1 in word:
            for g0 in B._merge_forced(B._split_marked(R.trim(mask[:, x0:x1]))):
                if g0.shape[0] >= 6 and g0.sum() >= 10:
                    out.extend(B._rescue_split(g0))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite-dir", default="/home/user/suites-seed1")
    ap.add_argument("--weights", default="models/glyphcnn-v3.npz")
    ap.add_argument("--limit", type=int, default=0, help="max items per suite (0=all)")
    a = ap.parse_args()

    net = PieceCNN(str(ROOT / a.weights))
    t0 = time.time()
    stats = {"items": 0, "aligned": 0, "n": 0, "ident": 0, "letter": 0,
             "case_ok": 0, "twin_n": 0, "twin_ok": 0, "misalign": 0}
    per_family = {}
    for suite in ("easy", "hard"):
        sdir = Path(a.suite_dir) / suite
        if not sdir.is_dir():
            continue
        import json as _json
        rows = [_json.loads(l) for l in open(sdir / "manifest.jsonl")]
        if a.limit:
            rows = rows[: a.limit]
        for r in rows:
            img = Image.open(sdir / "images" / f"{r['id']}.png")
            text, _ = B.read_text(img)
            if text != r["label"]:
                continue
            stats["items"] += 1
            pieces = pieces_for(img)
            chars = [c for c in r["label"] if not c.isspace()]
            if len(pieces) != len(chars):
                stats["misalign"] += 1
                continue
            stats["aligned"] += 1
            ops = net.opinions(pieces)
            fam = r["id"].rsplit("-", 1)[0]
            pf = per_family.setdefault(fam, [0, 0, 0, 0])  # n, ident, letter, case_ok
            for (pred, _p), ch in zip(ops, chars):
                stats["n"] += 1
                pf[0] += 1
                ok_ident = pred == ch
                ok_letter = pred.lower() == ch.lower()
                stats["ident"] += ok_ident
                stats["letter"] += ok_letter
                pf[1] += ok_ident
                pf[2] += ok_letter
                if ok_letter:
                    stats["case_ok"] += ok_ident
                    pf[3] += ok_ident
                    if ch.isalpha():  # every letter position is a case-twin position
                        stats["twin_n"] += 1
                        stats["twin_ok"] += ok_ident
    dt = time.time() - t0
    n, ident, letter, case_ok = stats["n"], stats["ident"], stats["letter"], stats["case_ok"]
    print(f"weights: {a.weights} | exact-read items: {stats['items']} "
          f"(aligned {stats['aligned']}, skipped misalign {stats['misalign']})")
    print(f"crops scored: {n}  ({dt:.0f}s)")
    if n:
        print(f"identity (char incl. case): {ident}/{n} = {ident/n:.3f}")
        print(f"letter (case-folded):       {letter}/{n} = {letter/n:.3f}")
        print(f"P(case correct | letter correct): {case_ok}/{letter}"
              f" = {case_ok/letter:.3f}" if letter else "no letter-correct crops")
        if stats["twin_n"]:
            print(f"  (letter positions only: {stats['twin_ok']}/{stats['twin_n']}"
                  f" = {stats['twin_ok']/stats['twin_n']:.3f})")
    print("\nper family (n, ident, letter, case_ok|letter):")
    for fam in sorted(per_family):
        fn, fi, fl, fc = per_family[fam]
        print(f"  {fam:12} {fn:5} {fi:5} {fl:5} {fc:5}"
              + (f"  case|letter={fc/fl:.3f}" if fl else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
