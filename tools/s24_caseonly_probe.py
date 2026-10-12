#!/usr/bin/env python3
"""S24 probe 3 (t-20261012-c4af, marcus): marginal value of v3 crop case
re-scoring on the classic stack's OWN case-only misses. NEGATIVE result.

Question: the S22 map says case-only is the biggest easy residue class (26
items pooled). Addendum 3 measured v3 case accuracy at 95.1% on crops from
EXACT-READ items. But a re-score would only be wired in where the stack is
WRONG — so the honest measurement is v3's accuracy on exactly those crops.

Method: take the committed floor+lex 3x receipt (barry's r1of3, easy 73 /
hard 21), select items whose miss is case-only (got.lower() == label.lower()),
re-segment each image with the classic pipeline (s24_realcrop_probe.pieces_for),
align pieces to label characters, and score PieceCNN(v3) per position:
  - stack-WRONG case positions: does v3 give the label's case?  (value)
  - stack-RIGHT case positions: does v3 keep it?                (regression)

Result (seed-1, 17/20 items aligned, 3 stitch items skipped — piece count
mismatch under stitch degradation):
  stack-WRONG positions: 18, v3 correct 8  = 44.4%
  stack-RIGHT positions: 377, v3 correct 349 = 92.6% (regression 7.4%)
  items helped >=1 position: 7/17 · items regressed >=1: 11/17
  => blind re-score fixes 8 and breaks 28: NET NEGATIVE.

Selection effect, named: the residue cases are the crops where case is
visually ambiguous — that is WHY the stack missed them. The 95% from
exact-read items does not transfer to the residue. Any wiring must be
confidence-gated and should be budgeted against 44%, not 95%.

Run:  python3 tools/s24_caseonly_probe.py --receipt reports/s22-3x/20261012T184402Z-easy-hard-r1of3.json \
        --suite-dir /home/user/suites-seed1 [--weights models/glyphcnn-v3.npz]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))
sys.path.insert(0, str(ROOT / "tools"))

from piece_cnn import PieceCNN  # noqa: E402
from s24_realcrop_probe import pieces_for  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True,
                    help="bench JSON receipt of the floor+lex route")
    ap.add_argument("--suite-dir", required=True)
    ap.add_argument("--weights", default="models/glyphcnn-v3.npz")
    a = ap.parse_args()

    net = PieceCNN(str(ROOT / a.weights))
    d = json.load(open(a.receipt))
    mm_tot = mm_ok = ok_tot = ok_ok = 0
    helped = hurt = aligned = skipped = 0
    for s in ("easy", "hard"):
        for r in d["suites"][s]["results"]:
            if r.get("excluded"):
                continue
            got, label = r["got"].strip(), r["label"]
            if got == label or got.lower() != label.lower():
                continue  # not a case-only miss
            img = Image.open(Path(a.suite_dir) / s / "images" / f"{r['id']}.png")
            pieces = pieces_for(img)
            chars = [c for c in label if not c.isspace()]
            gotc = [c for c in got if not c.isspace()]
            if len(pieces) != len(chars) or len(gotc) != len(chars):
                skipped += 1
                print(f"{r['id']}: SKIP alignment (pieces {len(pieces)} vs {len(chars)})")
                continue
            aligned += 1
            h = k = False
            for (pred, _p), gc, lc in zip(net.opinions(pieces), gotc, chars):
                if not lc.isalpha():
                    continue
                if gc != lc:
                    mm_tot += 1
                    mm_ok += pred == lc
                    h |= pred == lc
                else:
                    ok_tot += 1
                    ok_ok += pred == lc
                    k |= pred != lc
            helped += h
            hurt += k
    print(f"\naligned {aligned} case-only items (skipped {skipped})")
    if mm_tot:
        print(f"stack-WRONG case positions: {mm_tot}, v3 correct {mm_ok} = {mm_ok/mm_tot:.3f}")
    if ok_tot:
        print(f"stack-RIGHT case positions: {ok_tot}, v3 correct {ok_ok} = {ok_ok/ok_tot:.3f}"
              f" (blind-rescore regression {1-ok_ok/ok_tot:.3f})")
    print(f"items helped: {helped}/{aligned} · items regressed: {hurt}/{aligned}")
    net_fixes = mm_ok - (ok_tot - ok_ok)
    print(f"net positions: {net_fixes:+d} (fixes {mm_ok}, breaks {ok_tot-ok_ok})"
          f" -> {'NET NEGATIVE' if net_fixes < 0 else 'net positive'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
