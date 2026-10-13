#!/usr/bin/env python3
"""s54_c2_lex_ceiling.py — S54 C2a (t-20261013-768c): decompose the C1
composition ceiling and measure the lex-repair comparator.

C1 established: v7b composed at truth boxes = 0.537 word-exact (VAL
split). Before building a word model, decompose the gap:

  composed          word-exact (case-sensitive)        [C1: 0.537]
  composed-ci       case-INSENSITIVE word-exact        [letter-identity wall]
  +lex              composed + fix_token (the SHIPPING lex
                    projection rules, applied per word) [case-sensitive]
  +lex-ci           both                               [letters after lex]

If (+lex) recovers most of the case-insensitive ceiling, the word-model
lane reduces to case handling (closed lane, S55); if a large letter gap
remains after lex, a trained word model has real headroom.  All on the
same VAL split / same crops as C1. Diagnostics only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from readers.glyphcnn import GlyphCNN, index_to_char  # noqa: E402
from readers.segmentation import ink_mask, normalise_glyph  # noqa: E402
from lex_projection import fix_token  # noqa: E402
from s54_word_crops import word_groups, CTX_GLYPH  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/hard2000")
    ap.add_argument("--weights", default="models/glyphcnn-v7b.npz")
    ap.add_argument("--val-from", type=int, default=1600)
    ap.add_argument("--out", default="reports/s54-word-reader/c2_lex_ceiling.json")
    args = ap.parse_args()

    net = GlyphCNN.load(args.weights)
    rows = [json.loads(l) for l in open(Path(args.corpus) / "manifest.jsonl")]
    val = rows[args.val_from:]

    fam = defaultdict(lambda: defaultdict(int))
    total = defaultdict(int)
    for r in val:
        img = Image.open(Path(args.corpus) / r["image"])
        mask = ink_mask(img)
        H, W = mask.shape
        famkey = ("combined" if r["id"].startswith("combined")
                  else f"{r['degradation_type']}/{r['severity']}")
        for wlabel, wboxes in word_groups(r["label"], r["char_boxes"]):
            composed = []
            for ch, b in zip(wlabel, wboxes):
                X0, X1 = max(0, b[0] - CTX_GLYPH), min(W - 1, b[1] + CTX_GLYPH)
                Y0, Y1 = max(0, b[2] - CTX_GLYPH), min(H - 1, b[3] + CTX_GLYPH)
                crop = normalise_glyph(mask, (X0, Y0, X1, Y1))
                probs = net.forward(crop[None, None, :, :].astype(np.float32))[0][0]
                composed.append(index_to_char(int(probs.argmax())))
            got = "".join(composed)
            lexed = fix_token(got)
            for name, val_ in (
                    ("composed", got == wlabel),
                    ("composed_ci", got.lower() == wlabel.lower()),
                    ("lex", lexed == wlabel),
                    ("lex_ci", lexed.lower() == wlabel.lower())):
                fam[famkey][name] += int(val_)
                fam[famkey][name + "_n"] += 1
                total[name] += int(val_)
                total[name + "_n"] += 1

    out = {"total": {k: round(total[k] / total[k + "_n"], 4)
                     for k in ("composed", "composed_ci", "lex", "lex_ci")},
           "n_words": total["composed_n"], "per_family": {}}
    print(f"n words: {total['composed_n']}")
    print(f"{'family':28s} {'composed':>9s} {'comp-ci':>8s} {'+lex':>7s} {'lex-ci':>8s}")
    for k in sorted(fam):
        d = fam[k]
        row = {m: round(d[m] / d[m + "_n"], 4)
               for m in ("composed", "composed_ci", "lex", "lex_ci")}
        out["per_family"][k] = row
        print(f"{k:28s} {row['composed']:9.3f} {row['composed_ci']:8.3f} "
              f"{row['lex']:7.3f} {row['lex_ci']:8.3f}")
    print(f"{'TOTAL':28s} {out['total']['composed']:9.3f} "
          f"{out['total']['composed_ci']:8.3f} {out['total']['lex']:7.3f} "
          f"{out['total']['lex_ci']:8.3f}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"report {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
