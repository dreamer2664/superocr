#!/usr/bin/env python3
"""S31 lever-1 (t-20261013-becc): word-context crops at read time, OFF/ON probe.

Question: v7b was trained on truth advance boxes ±1px (word-context semantics
from the S53 corpus — neighbour ink at the edges), but the shipping floor feeds
tight solo pieces. Does giving the SAME floor pieces ±K px of context at read
time recover part of v7b's crop-level gains at read level?

Design (one variable isolated): the pieces are the FLOOR'S OWN, bit-exact
(corrosion_cnn.floor_pieces under the same seed-1 inputs — same mask, same
segmentation, same split/merge). Only the crop window changes:
  - control arm K0: crop_of(piece) — literal S30-probe semantics; must
    reproduce easy 31/100 (v7b) / hard 7/100 (v7b) exact from reports/s30-v7b
  - context arms: each piece is PLACED at its true (row, col) location in the
    floor mask by exact equality search (piece packs are trimmed copies of
    mask windows), then cropped with ±K px on all four sides and normalised
    through the same normalise_glyph path.
Honesty note — virtual-merge pieces: when reader.merge_forced abuts two packs
(re-registering them to a shared top row), the merged pack has no exact sheet
location; such pieces are disclosed per run and receive the tight crop in
every arm (no context), so they can only contribute a small common-mode
conservatism to the K-delta, never a false positive.

Arms (fixed up-front): ctrl-v7b-K0 | ctx-v7b-K1 | ctx-v7b-K2 | ctx-v4-K1
(contrast: is any gain v7b-specific or pure geometry?).
Metrics per suite: exact (raw CNN chain, no fix_line — S30 read-probe
semantics), mean char acc, per-family exact table, placement coverage.

Usage: python3 tools/s31_v7b_context_probe.py --suites /tmp/s8 --out rows.jsonl [--only hard]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import reader as R                                          # noqa: E402
from importlib.util import spec_from_file_location, module_from_spec  # noqa: E402
from readers.glyphcnn import GlyphCNN, index_to_char        # noqa: E402

_spec = spec_from_file_location("cc", HERE / "corrosion_cnn.py")
cc = module_from_spec(_spec)
_spec.loader.exec_module(cc)                                # floor_pieces / crop_of / normalise_glyph / _char_acc


def place_pieces(mask: np.ndarray, pieces: list[np.ndarray],
                 word_of: list[int]) -> list[tuple[int, int, int, int] | None]:
    """Exact (row, col) placement of every floor piece inside its word span.
    Returns boxes or None for virtual-merge pieces (no exact location)."""
    H = mask.shape[0]
    spans = [w for w in R.segment(mask)]
    words_xy = [(w[0][0], w[-1][1]) for w in spans]
    boxes: list[tuple[int, int, int, int] | None] = []
    counts = {}
    for w in word_of:
        counts[w] = counts.get(w, 0) + 1
    pi = 0
    for w in sorted(counts):
        k = counts[w]
        sx0, sx1 = words_xy[w]
        start = sx0
        for _ in range(k):
            p = pieces[pi]
            ph, pw = p.shape
            hit = None
            for oc in range(start, sx1 - pw + 1):
                sub = mask[:, oc:oc + pw]
                for dr in range(0, H - ph + 1):
                    if np.array_equal(sub[dr:dr + ph, :], p):
                        hit = (oc, oc + pw, dr, dr + ph)
                        break
                if hit:
                    break
            if hit:
                boxes.append(hit)
                start = hit[1]
            else:
                boxes.append(None)
            pi += 1
    return boxes


def context_crop(mask: np.ndarray, box: tuple[int, int, int, int], K: int) -> np.ndarray:
    xc0, xc1, yr0, yr1 = box
    H, W = mask.shape
    win = mask[max(0, yr0 - K):min(H, yr1 + K), max(0, xc0 - K):min(W, xc1 + K)]
    win = R.trim(win)
    h, w = win.shape
    return cc.normalise_glyph(win, (0, 0, w - 1, h - 1))  # 2D, like crop_of(p)[0]


def char_acc(label: str, text: str) -> float:
    l1, l2 = label.replace(" ", ""), text.replace(" ", "")
    tot = max(len(l1), len(l2)) or 1
    return sum(a == b for a, b in zip(l1, l2)) / tot


def read_arm(img: Image.Image, net: GlyphCNN, K: int | None,
             stats: dict) -> str:
    mask, pieces, word_of = cc.floor_pieces(img)
    if not pieces:
        return ""
    if K is None:  # control: literal floor semantics
        crops = np.stack([cc.crop_of(p)[0] for p in pieces])
    else:
        boxes = place_pieces(mask, pieces, word_of)
        stats["placed"] += sum(b is not None for b in boxes)
        stats["virtual"] += sum(b is None for b in boxes)
        crops = np.stack([
            context_crop(mask, b, K) if b is not None else cc.crop_of(p)[0]
            for b, p in zip(boxes, pieces)])
    probs = net.forward(crops[:, None, :, :].astype(net.p["w1"].dtype))[0]
    out: list[str] = []
    last = word_of[0]
    for j in range(len(pieces)):
        if word_of[j] != last:
            out.append(" ")
            last = word_of[j]
        out.append(index_to_char(int(probs[j].argmax())))
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["easy", "hard"], default=None)
    args = ap.parse_args()

    root = Path(args.suites)
    nets = {
        "v7b": GlyphCNN.load(str(HERE.parent / "models" / "glyphcnn-v7b.npz")),
        "v4": GlyphCNN.load(str(HERE.parent / "models" / "glyphcnn-v4.npz")),
    }
    arms = [("ctrl-v7b-K0", "v7b", None), ("ctx-v7b-K1", "v7b", 1),
            ("ctx-v7b-K2", "v7b", 2), ("ctx-v4-K1", "v4", 1)]
    suites = [args.only] if args.only else ["easy", "hard"]
    stats = {"placed": 0, "virtual": 0}
    t_start = time.time()
    rows = 0
    with open(args.out, "w") as fh:
        for suite in suites:
            items = [json.loads(l) for l in open(root / suite / "manifest.jsonl")]
            for it in items:
                img = Image.open(root / suite / it["image"]).convert("RGB")
                for arm, net_name, K in arms:
                    t0 = time.perf_counter()
                    got = read_arm(img, nets[net_name], K, stats)
                    sec = round(time.perf_counter() - t0, 3)
                    fh.write(json.dumps({
                        "suite": suite, "id": it["id"],
                        "family": it.get("family", suite), "arm": arm,
                        "label": it["label"], "got": got,
                        "exact": got == it["label"],
                        "char": round(char_acc(it["label"], got), 4),
                        "sec": sec,
                    }) + "\n")
                    fh.flush()
                    rows += 1
        fh.write(json.dumps({"event": "done", "rows": rows,
                             "places": stats,
                             "wall_s": round(time.time() - t_start, 1)}) + "\n")
    print(f"wrote {rows} rows (+footer) to {args.out}; placements {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
