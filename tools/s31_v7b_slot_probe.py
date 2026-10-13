#!/usr/bin/env python3
"""S31 lever-2 (t-20261013-becc): v7b in the shipping chain's CNN slot, OFF/ON probe.

Question: does swapping the rerank/piece CNN's weights from glyphcnn-v2
(shipping) to glyphcnn-v7b (S30, corpus-retrained) move the SHIPPING route
(baseline.read_text -> lex_projection.fix_line), and where does it hurt?

Context: S30 receipts show v7b beats v4/v2-class checkpoints on every crop
distribution (corpus val 0.43->0.80, easy glyph 0.9009->0.9235) but the raw
read-level hard exact barely moves (6->7) through the tight solo-piece chain.
This probe measures the lexicon-path integration: same floor, same gates,
same fix_line — the CNN opinion changes weights only.

Protocol (fixed up-front):
  arms = off (shipping v2 slot) | v7b-slot (same chain, v7b injected into
         baseline's CNN cache before the first read; gate params unchanged)
  route = B.read_text(img, None) -> fix_line, in-process mirror of the
         shipping wrapper (semantics verified byte-equal in s22/s38/w1 receipts)
  data  = canonical seed-1, dir_hash-verified by caller; OFF arm must
         reproduce easy 73 / hard 23 exactly or the harness is void
  output = jsonl rows + done footer; family x arm table produced by the report

Injection note: we set baseline._CNN directly (same object the rerank gate
calls at baseline.py:280); nothing is written to the tree, the shipping
reader is untouched, and the swap is probe-process-local by construction.
The PieceCNN piece-policy stays OFF, exactly as shipped (SUPEROCR_PIECE_CNN
unset) — this measures the shipping gates only.

Usage: python3 tools/s31_v7b_slot_probe.py --suites /tmp/s8 --out rows.jsonl [--only easy|hard]
"""
import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import baseline as B                       # noqa: E402
from lex_projection import fix_line        # noqa: E402
from readers.glyphcnn import GlyphCNN      # noqa: E402


def inject_v7b() -> None:
    """Replace the shipping CNN opinion with v7b for this process only."""
    B._CNN = GlyphCNN.load(str(HERE.parent / "models" / "glyphcnn-v7b.npz"))


ARMS = ["off", "v7b-slot"]


def read_route(img: Image.Image) -> str:
    text, _conf = B.read_text(img.convert("RGB"), None)
    return fix_line(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["easy", "hard"], default=None)
    args = ap.parse_args()

    root = Path(args.suites)
    suites = [args.only] if args.only else ["easy", "hard"]
    t_start = time.time()
    rows = 0
    with open(args.out, "w") as fh:
        for arm in ARMS:
            if arm == "v7b-slot":
                inject_v7b()
            for suite in suites:
                items = [json.loads(l) for l in open(root / suite / "manifest.jsonl")]
                for it in items:
                    img = Image.open(root / suite / it["image"]).convert("RGB")
                    t0 = time.perf_counter()
                    got = read_route(img)
                    sec = round(time.perf_counter() - t0, 3)
                    fh.write(json.dumps({
                        "suite": suite, "id": it["id"],
                        "family": it.get("family", suite), "arm": arm,
                        "label": it["label"], "got": got,
                        "exact": got == it["label"], "sec": sec,
                    }) + "\n")
                    fh.flush()
                    rows += 1
        fh.write(json.dumps({"event": "done", "rows": rows,
                             "wall_s": round(time.time() - t_start, 1)}) + "\n")
    print(f"wrote {rows} rows (+footer) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
