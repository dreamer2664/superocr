#!/usr/bin/env python3
"""cnn_reader.py — end-to-end reader: image in, text out (t-20261011-f0d2).

    python3 readers/cnn_reader.py --image path/to/image.png
    python3 readers/cnn_reader.py --image x.jpg --debug      # boxes + confidences
    python3 readers/cnn_reader.py --image x.jpg --weights models/glyphcnn.npz

stdout is exactly the recognised text (the bench protocol): segmentation ->
per-glyph classification -> characters in reading order, spaces where the
segmenter saw a word gap. No lexicon, no language model, no guessing: what
the network saw is what you get. That is the honest baseline the S2 chain is
supposed to beat; `--debug` shows where it fails.

Deterministic: same image + same weights -> same text.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "readers"))

from glyphcnn import GlyphCNN, index_to_char          # noqa: E402
from segmentation import analyse, normalise_glyph      # noqa: E402

DEFAULT_WEIGHTS = str(ROOT / "models" / "glyphcnn.npz")


def read_image(path: str, weights: str, debug: bool = False) -> str:
    if not os.path.exists(weights):
        raise SystemExit(f"cnn_reader: no weights at {weights} "
                         f"(run: python3 tools/train_glyphs.py)")
    net = GlyphCNN.load(weights)

    t0 = time.perf_counter()
    with Image.open(path) as img:
        img = img.convert("RGB")
        mask, boxes = analyse(img)
    t_seg = time.perf_counter() - t0

    if not boxes:
        if debug:
            print(f"[cnn] no glyph boxes found in {path}", file=sys.stderr)
        return ""

    crops = np.stack([normalise_glyph(mask, box) for box, _ in boxes])[:, None, :, :]
    t0 = time.perf_counter()
    probs = net.forward(crops.astype(net.p["w1"].dtype))[0]
    t_cls = time.perf_counter() - t0

    out = []
    for i, (_, space_before) in enumerate(boxes):
        idx = int(probs[i].argmax())
        ch = index_to_char(idx)
        if space_before and out and out[-1] != " ":
            out.append(" ")
        out.append(ch)
        if debug:
            print(f"[cnn] box {i:2}: {ch!r} p={probs[i][idx]:.3f}", file=sys.stderr)
    text = "".join(out)
    if debug:
        print(f"[cnn] {len(boxes)} glyphs | segment {t_seg*1000:.0f}ms, "
              f"classify {t_cls*1000:.0f}ms | {text!r}", file=sys.stderr)
    return text


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--image", required=True)
    p.add_argument("--weights", default=DEFAULT_WEIGHTS)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    try:
        text = read_image(args.image, args.weights, args.debug)
    except FileNotFoundError as e:
        print(f"cnn_reader: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
