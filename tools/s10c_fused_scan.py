#!/usr/bin/env python3
"""s10c_fused_scan.py — find fused-join candidates on a suite (S10c prep).

A "fused join" is a piece the segmenter kept whole but which holds two (or
more) touching glyphs: the template read of the fused piece is usually a
single confident wrong character ('rb'->I, 'al'->b, 'rf'->H).

This scanner does NOT decide anything. It walks the floor's own pieces
(same chain as baseline.read_text), and reports every piece that could
plausibly hide a join, with the numbers needed to rank it:

  * item id, currently exact/wrong, label and floor read,
  * piece index, width/height/aspect, template answer and score,
  * the deepest column-profile minima inside the piece (candidate cuts),
  * the CNN's answer + probability on the piece as-is.

Output: JSON + a short table. Run on a quiet box (it is a full pass over the
suite through the floor chain).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "readers"))

from s10b_gate import chain_pieces, apply_case  # noqa: E402
from piece_cnn import PieceCNN  # noqa: E402
import baseline as B  # noqa: E402


def profile_minima(piece: np.ndarray, max_cuts: int = 12) -> list[int]:
    """Column indices of the deepest interior minima of the smoothed column
    profile - the same signal the matcher-side rescue uses."""
    h, w = piece.shape
    if w < 8:
        return []
    cols = piece.sum(axis=0).astype(np.float32)
    k = np.ones(3, dtype=np.float32) / 3.0
    smooth = np.convolve(cols, k, mode="same")
    lo, hi = max(2, w // 5), min(w - 2, (w * 4) // 5)
    idx = [i for i in range(lo, hi + 1)
           if smooth[i] <= smooth[i - 1] and smooth[i] <= smooth[i + 1]]
    idx.sort(key=lambda i: smooth[i])
    return sorted(idx[:max_cuts])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite-dir", default="/tmp/s10-suites")
    ap.add_argument("--suite", default="easy")
    ap.add_argument("--weights", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-aspect-gate", type=float, default=0.85,
                    help="report pieces wider than this * height (rescue's gate)")
    ap.add_argument("--conf-gate", type=float, default=0.72,
                    help="report pieces matching below this confidence")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    net = PieceCNN(args.weights)
    base = Path(args.suite_dir) / args.suite
    manifest = [json.loads(l) for l in (base / "manifest.jsonl").read_text().splitlines()
                if l.strip()]
    if args.limit:
        manifest = manifest[:args.limit]

    out = []
    for n, item in enumerate(manifest, 1):
        with Image.open(base / item["image"]) as im:
            im = im.convert("RGB")
            words = chain_pieces(im)
        pieces = [g for w in words for g in w]
        floor_text = None
        cands = []
        ops = net.opinions(pieces)
        for i, (g, (cch, cp)) in enumerate(zip(pieces, ops)):
            h, w = g.shape
            ch, s = B.match_native(g)
            aspect = w / max(h, 1)
            if not (s < args.conf_gate or aspect > args.max_aspect_gate):
                continue
            cuts = profile_minima(g)
            cands.append({
                "piece": i, "h": int(h), "w": int(w),
                "aspect": round(aspect, 3),
                "tmpl_ch": ch, "tmpl_score": round(float(s), 4),
                "cnn_ch": cch, "cnn_p": round(float(cp), 4),
                "cuts": cuts,
            })
        if cands:
            out.append({"id": item["id"], "label": item["label"],
                        "candidates": cands})
        if n % 25 == 0:
            print(f"  [{args.suite}] {n}/{len(manifest)}", flush=True)

    n_items = len(out)
    print(f"\n{args.suite}: {n_items}/{len(manifest)} items have >=1 fused/suspect piece")
    for row in out[:20]:
        c = row["candidates"][0]
        print(f"  {row['id']:12s} pieces={len(row['candidates'])} "
              f"first: {c['w']}x{c['h']} tmpl={c['tmpl_ch']!r}/{c['tmpl_score']} "
              f"cnn={c['cnn_ch']!r}/{c['cnn_p']} cuts={c['cuts'][:6]}")
    if args.json:
        json.dump(out, open(args.json, "w"), indent=1)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
