#!/usr/bin/env python3
"""S25 (t-20261013-0956): piece-count gap on the hard residue.

Two modes:

  --collect  run the shipping route (tools/reader_lex.py, subprocess) on every
             hard-suite image and, in the same pass, replicate baseline's mask
             construction to record the reader's word-piece structure. Writes
             one jsonl row per item:

               id family want got exact
               reader_words      R.segment() word count on the route's mask
               glyph_pieces      glyphs per word (len list)
               label_tokens      len(want.split())

  (default)   read the collected jsonl and print the gap classification:
               fewer / more / equal pieces vs label tokens, cross-tabbed with
               exactness and family, plus the token-level residue (which label
               tokens are missing from got, which got tokens are extra).

The mask replication imports baseline and reuses its own internals
(_family_mask with family=None, the S8 threshold lean, the polarity guard,
despeck/trim/deskew) so the recorded piece structure is the shipping route's,
not an approximation.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402  (route internals)
import reader as R  # noqa: E402


def route_pieces(img: Image.Image) -> tuple[int, list[int]]:
    """Replicate read_text's mask path; return (word count, glyphs per word)."""
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
    words = R.segment(mask)
    return len(words), [len(w) for w in words]


def collect(out: Path, suite: str) -> int:
    man = ROOT / "data" / suite / "manifest.jsonl"
    rows = []
    for line in man.read_text().splitlines():
        m = json.loads(line)
        img_path = ROOT / "data" / suite / m["image"]
        got = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "reader_lex.py"), str(img_path)],
            capture_output=True, text=True)
        if got.returncode != 0:
            sys.stderr.write(got.stderr)
            return got.returncode
        text = got.stdout.strip()
        nw, glyphs = route_pieces(Image.open(img_path))
        rows.append({
            "id": m["id"], "family": m["family"], "want": m["label"],
            "got": text, "exact": text == m["label"],
            "reader_words": nw, "glyph_pieces": glyphs,
            "label_tokens": len(m["label"].split()),
        })
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n_ex = sum(r["exact"] for r in rows)
    print(f"{suite}: {len(rows)} items, {n_ex} exact -> {out}")
    return 0


def _subseq_class(want: list[str], got: list[str]) -> str:
    """Token-level relationship of got to want (order-preserving)."""
    i = 0
    missing = []
    for w in want:
        if i < len(got) and got[i] == w:
            i += 1
        else:
            missing.append(w)
    extra = got[i:]
    if not missing and not extra:
        return "subsequence-clean"
    return f"missing={missing} extra={extra}"


def analyse(rows: list[dict]) -> None:
    miss = [r for r in rows if not r["exact"]]
    print(f"\n{len(rows)} items, {len(rows) - len(miss)} exact, {len(miss)} misses\n")

    cls = Counter()
    fam_cls = defaultdict(Counter)
    print(f"{'id':<18} {'fam':<13} {'rw':>3} {'lt':>3}  class")
    for r in sorted(miss, key=lambda r: (r["family"], r["id"])):
        rw, lt = r["reader_words"], r["label_tokens"]
        c = ("equal" if rw == lt else
             "fewer" if rw < lt else "more")
        cls[c] += 1
        fam_cls[r["family"]][c] += 1
        print(f"{r['id']:<18} {r['family']:<13} {rw:>3} {lt:>3}  {c:<6} "
              f"| {r['subseq']}")
    print("\npiece-count classes on the residue:", dict(cls))
    print("\nper family (misses: fewer/more/equal):")
    for fam in sorted(fam_cls):
        c = fam_cls[fam]
        print(f"  {fam:<13} {sum(c.values()):>2}  "
              f"{c['fewer']:>2}/{c['more']:>2}/{c['equal']:>2}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--suite", default="hard")
    ap.add_argument("--jsonl",
                    default="reports/s25-piece-gap/hard-reads.jsonl")
    a = ap.parse_args()
    out = ROOT / a.jsonl
    if a.collect:
        return collect(out, a.suite)
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    for r in rows:
        r["subseq"] = _subseq_class(r["want"].split(), r["got"].split())
    analyse(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
