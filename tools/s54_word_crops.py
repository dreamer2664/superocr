#!/usr/bin/env python3
"""s54_word_crops.py — S54 (t-20261013-768c) Checkpoint 1: the word-crop
contract + the ORACLE word-read ceiling. Diagnostics only — no reader is
changed, nothing ships from this file.

THE CONTRACT (for achilles's S56 read-time segmenter):
  A "word crop" is the axis-aligned bounding box of one truth word's
  char_boxes (min x0, max x1, min y0, max y1) expanded by CTX px of
  context on every side, cut from the reader's ink mask (ink_mask, the
  same front end the floor uses), then JOINTLY normalised: the whole
  word is scaled to a fixed height WORD_H=32 px (BILINEAR, aspect
  preserved — width varies, one scale for ALL glyphs in the word: the
  "advances-vs-ink semantics fixed once" from the task spec).  Word
  labels are the space-split label tokens; char_boxes give per-glyph
  truth INSIDE the word crop (x-offsets recomputed after the joint
  scaling) so a word model can be trained per-position without
  re-deriving segmentation.

ORACLE WORD-READ (the ceiling measurement):
  Per glyph: crop the truth box ±CTX_GLYPH px from the ink mask,
  classify with the committed glyphcnn-v7b (merged lineage), no lexicon.
  A word is oracle-exact iff every glyph opinion is correct.  This is
  the upper bound for ANY word-segmentation fix given the current
  classifier — it says whether the wall is still the classifier or has
  moved to segmentation.  Truth boxes are oracle diagnostics, not a
  shipping reader result (per task spec).

Held-out discipline: numbers are reported on the S53 corpus VAL split
(items 1600-1999) per the binding held-out protocol; canonical suites
are eval-only and are not touched here.
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

from readers.glyphcnn import GlyphCNN, char_to_index, index_to_char  # noqa: E402
from readers.segmentation import ink_mask, normalise_glyph  # noqa: E402

WORD_H = 32
CTX_WORD = 3      # context px around the merged word box
CTX_GLYPH = 1     # context px around each glyph box (v7b's training spec)


def word_groups(label: str, boxes: list[list[int]]):
    """Yield (word_label, [box,...]) per space-split token, in order."""
    words = []
    glyphs = [c for c in label if c != " "]
    assert len(glyphs) == len(boxes), "box/glyph count mismatch"
    i = 0
    for tok in label.split(" "):
        n = len(tok)
        words.append((tok, boxes[i:i + n]))
        i += n
    return words


def word_box(wboxes, W, H):
    x0 = min(b[0] for b in wboxes)
    x1 = max(b[1] for b in wboxes)
    y0 = min(b[2] for b in wboxes)
    y1 = max(b[3] for b in wboxes)
    return max(0, x0 - CTX_WORD), min(W - 1, x1 + CTX_WORD), \
        max(0, y0 - CTX_WORD), min(H - 1, y1 + CTX_WORD)


def oracle_word_read(mask, wboxes, wlabel, net):
    """Per-glyph v7b opinions at truth boxes; word exact iff all right."""
    H, W = mask.shape
    hits, total = 0, 0
    ok = True
    for ch, b in zip(wlabel, wboxes):
        X0, X1 = max(0, b[0] - CTX_GLYPH), min(W - 1, b[1] + CTX_GLYPH)
        Y0, Y1 = max(0, b[2] - CTX_GLYPH), min(H - 1, b[3] + CTX_GLYPH)
        crop = normalise_glyph(mask, (X0, Y0, X1, Y1))
        probs = net.forward(crop[None, None, :, :].astype(np.float32))[0][0]
        got = index_to_char(int(probs.argmax()))
        total += 1
        hits += got == ch
        ok = ok and got == ch
    return ok, hits, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/hard2000")
    ap.add_argument("--weights", default="models/glyphcnn-v7b.npz")
    ap.add_argument("--val-from", type=int, default=1600)
    ap.add_argument("--sample-out", default="reports/s54-word-reader/sample")
    ap.add_argument("--out", default="reports/s54-word-reader/checkpoint1.json")
    args = ap.parse_args()

    net = GlyphCNN.load(args.weights)
    rows = [json.loads(l) for l in open(Path(args.corpus) / "manifest.jsonl")]
    val = rows[args.val_from:]
    print(f"S53 corpus: {len(rows)} items; VAL split {args.val_from}: "
          f"{len(val)} items (held-out by index)", flush=True)

    fam = defaultdict(lambda: {"words": 0, "word_exact": 0,
                               "glyph_hits": 0, "glyph_total": 0})
    sample_dir = Path(args.sample_out)
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_idx = []
    taken = defaultdict(int)

    for r in val:
        img = Image.open(Path(args.corpus) / r["image"])
        mask = ink_mask(img)
        H, W = mask.shape
        famkey = ("combined" if r["id"].startswith("combined")
                  else f"{r['degradation_type']}/{r['severity']}")
        for wi, (wlabel, wboxes) in enumerate(word_groups(r["label"],
                                                          r["char_boxes"])):
            ok, hits, total = oracle_word_read(mask, wboxes, wlabel, net)
            f = fam[famkey]
            f["words"] += 1
            f["word_exact"] += int(ok)
            f["glyph_hits"] += hits
            f["glyph_total"] += total
            # contract sample: 2 per family
            if taken[famkey] < 2 and mask is not None:
                bx0, bx1, by0, by1 = word_box(wboxes, W, H)
                crop = mask[by0:by1 + 1, bx0:bx1 + 1]
                if crop.any():
                    im = Image.fromarray((crop * 255).astype(np.uint8), "L")
                    w2 = max(1, round(im.width * WORD_H / im.height))
                    im = im.resize((w2, WORD_H), Image.BILINEAR)
                    fn = f"{r['id']}-w{wi}.png"
                    im.save(sample_dir / fn)
                    sample_idx.append({"file": f"sample/{fn}", "word": wlabel,
                                       "family": famkey,
                                       "h": im.height, "w": im.width})
                    taken[famkey] += 1

    out = {}
    print(f"\n{'family':28s} {'word-exact':>12s} {'glyph-acc':>10s}")
    for k in sorted(fam):
        f = fam[k]
        we = f["word_exact"] / f["words"]
        ga = f["glyph_hits"] / f["glyph_total"]
        out[k] = {"words": f["words"], "word_exact": round(we, 4),
                  "glyph_acc": round(ga, 4), "glyph_total": f["glyph_total"]}
        print(f"{k:28s} {f['word_exact']:5d}/{f['words']:<6d} {ga:10.4f}")
    tot_w = sum(f["words"] for f in fam.values())
    tot_we = sum(f["word_exact"] for f in fam.values())
    tot_g = sum(f["glyph_hits"] for f in fam.values())
    tot_gt = sum(f["glyph_total"] for f in fam.values())
    out["_TOTAL"] = {"words": tot_w, "word_exact": round(tot_we / tot_w, 4),
                     "glyph_acc": round(tot_g / tot_gt, 4)}
    print(f"{'TOTAL':28s} {tot_we:5d}/{tot_w:<6d} {tot_g/tot_gt:10.4f}")

    json.dump({"contract": {"word_h": WORD_H, "ctx_word": CTX_WORD,
                            "ctx_glyph": CTX_GLYPH,
                            "mask": "readers.segmentation.ink_mask",
                            "weights": args.weights,
                            "split": f"items {args.val_from}+ (val)"},
               "per_family": out,
               "sample_index": sample_idx},
              open(args.out, "w"), indent=1)
    json.dump(sample_idx, open(sample_dir / "index.json", "w"), indent=1)
    print(f"\nreport {args.out}; {len(sample_idx)} contract samples in {args.sample_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
