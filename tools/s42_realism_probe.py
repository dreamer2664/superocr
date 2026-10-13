#!/usr/bin/env python3
"""s42_realism_probe.py — S42 receipts: reader sensitivity + the S43
realism metric on the realism corpus.

S43's census: 63/77 hard misses are SEGMENTATION failures. A degradation
family is "realistic" (matches real failure modes) to the extent it makes
the floor's piece count diverge from the true glyph count — that, not
cosmetic damage, is what the 98/95 bar is fighting. So per cell we report:

  seg_align : % of items where floor_pieces count == true glyph count
  exact     : reader_lex exact match (shipping route, 12/cell sample)

plus control as the contrast arm.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("cc", ROOT / "tools" / "corrosion_cnn.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)  # floor_pieces


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/real10k")
    ap.add_argument("--per-cell", type=int, default=12)
    ap.add_argument("--out", default="reports/s42-real-corpus/sensitivity.json")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(Path(args.corpus) / "manifest.jsonl")]
    cells = defaultdict(list)
    for r in rows:
        cells[f"{r['degradation_type']}/{r['severity']}"].append(r)

    rng = random.Random(7)
    out = {}
    print(f"{'cell':30s} {'seg_align':>9s} {'exact':>10s}")
    for key in sorted(cells):
        pool = cells[key]
        sample = rng.sample(pool, min(args.per_cell, len(pool)))
        aligned = 0
        exact = 0
        for r in sample:
            img = Image.open(Path(args.corpus) / r["image"])
            glyphs = [c for c in r["label"] if c != " "]
            _, pieces, _ = cc.floor_pieces(img)
            if len(pieces) == len(glyphs):
                aligned += 1
            p = subprocess.run([sys.executable, "tools/reader_lex.py",
                                str(Path(args.corpus) / r["image"])],
                               capture_output=True, text=True)
            if p.returncode == 0 and p.stdout.strip() == r["label"]:
                exact += 1
        n = len(sample)
        out[key] = {"n": n, "seg_align": round(aligned / n, 4),
                    "exact": round(exact / n, 4)}
        print(f"{key:30s} {aligned:>4d}/{n:<4d}  {exact:>4d}/{n:<4d}", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"report {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
