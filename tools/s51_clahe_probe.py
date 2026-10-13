#!/usr/bin/env python3
"""S51 (t-20261013-03e8): CLAHE pre-step probe — OFF vs ON arms, no reader change.

Task: "Some families have very low contrast. Implement CLAHE (Contrast Limited
Adaptive Histogram Equalization). Test on all families."

Design (fixed up-front before any numbers were seen — dev discipline):
  arms   = off | clahe-2.0 | clahe-4.0   (grid 8x8 tiles, 256-bin, luminance)
  route  = the SHIPPING wrapper semantics, mirrored in-process:
           baseline.read_text(img, None) -> tools.lex_projection.fix_line
           (verified byte-equal to `python3 tools/reader_lex.py {image}`)
  data   = canonical seed-1 suites only (dir_hash verified by caller receipts)
  output = jsonl rows {suite,id,family,arm,label,got,exact,sec} + summary footer

CLAHE implementation: hand-rolled numpy (repo constraint: stdlib+numpy/Pillow,
no cv2 in tree). Standard formulation: per-tile histogram, clip at
clip*mean_bin_mass, uniform redistribution of clipped mass, tile CDFs,
bilinear interpolation across tile centers. Deterministic; identical inputs
produce identical outputs bit-for-bit.

Honesty notes:
- The 'off' arm is the internal control: on canonical seed-1 it must
  reproduce the settled shipping line (easy 73/100, hard 23/100) exactly;
  if it does not, the harness is broken and the arms say nothing.
- CLAHE is applied to the luminance and the image is rebuilt as grayscale
  RGB closer to the working-point of the binarizer; colour channels of the
  original are not preserved. That is the probe's honest cheapest form.
- Nothing here changes the shipping reader. Integration is a separate task
  and happens only if arms justify it ON the dev view, per held-out protocol.

Usage: python3 tools/s51_clahe_probe.py --suites /tmp/s8 --out /tmp/s51-probe.jsonl [--only easy|hard]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))      # repo root for baseline
sys.path.insert(0, str(HERE))             # tools/ for lex_projection

import baseline as B                      # noqa: E402
from lex_projection import fix_line       # noqa: E402


def clahe(img: Image.Image, grid: int = 8, clip: float = 2.0) -> Image.Image:
    """Contrast-limited adaptive histogram equalization on luminance.

    grid: tiles per side. clip: multiple of the mean tile-bin mass.
    Returns grayscale RGB image. Deterministic.
    """
    g = np.asarray(img.convert("L"), dtype=np.float64)
    h, w = g.shape
    th, tw = h // grid, w // grid
    # tile-centered grid of CDFs, shape (grid, grid, 256)
    cdfs = np.zeros((grid, grid, 256), dtype=np.float64)
    for ty in range(grid):
        for tx in range(grid):
            tile = g[ty * th:(ty + 1) * th, tx * tw:(tx + 1) * tw]
            hist = np.bincount(tile.astype(np.uint8).ravel(), minlength=256).astype(np.float64)
            limit = clip * hist.mean()
            excess = np.clip(hist - limit, 0.0, None)
            hist = np.minimum(hist, limit)
            hist += excess.sum() / 256.0
            cdf = np.cumsum(hist)
            cdf /= cdf[-1] if cdf[-1] > 0 else 1.0
            cdfs[ty, tx] = cdf
    # bilinear interpolation between tile centers (edge tiles replicate)
    bin_idx = g.astype(np.uint8).astype(np.int64)
    out = np.zeros_like(g)
    ys = (np.arange(h, dtype=np.float64) / max(th, 1)) - 0.5
    xs = (np.arange(w, dtype=np.float64) / max(tw, 1)) - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, grid - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, grid - 1)
    y1 = np.clip(y0 + 1, 0, grid - 1)
    x1 = np.clip(x0 + 1, 0, grid - 1)
    fy = np.clip(ys - np.floor(ys), 0.0, 1.0)[:, None]
    fx = np.clip(xs - np.floor(xs), 0.0, 1.0)[None, :]
    c00 = cdfs[y0[:, None], x0[None, :], bin_idx]
    c01 = cdfs[y0[:, None], x1[None, :], bin_idx]
    c10 = cdfs[y1[:, None], x0[None, :], bin_idx]
    c11 = cdfs[y1[:, None], x1[None, :], bin_idx]
    top = c00 * (1 - fx) + c01 * fx
    bot = c10 * (1 - fx) + c11 * fx
    out = top * (1 - fy) + bot * fy
    lu = (np.clip(out, 0.0, 1.0) * 255.0).round().astype(np.uint8)
    return Image.fromarray(np.stack([lu, lu, lu], axis=-1), "RGB")


ARMS = {
    "off": lambda img: img,
    "clahe-2.0": lambda img: clahe(img, 8, 2.0),
    "clahe-4.0": lambda img: clahe(img, 8, 4.0),
}


def read_route(img: Image.Image) -> str:
    text, _conf = B.read_text(img.convert("RGB"), None)
    return fix_line(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", required=True, help="suite root containing easy/ and hard/")
    ap.add_argument("--out", required=True, help="jsonl output path")
    ap.add_argument("--only", choices=["easy", "hard"], default=None)
    args = ap.parse_args()

    root = Path(args.suites)
    suites = [args.only] if args.only else ["easy", "hard"]
    t_start = time.time()
    rows = 0
    with open(args.out, "w") as fh:
        for suite in suites:
            manifest = root / suite / "manifest.jsonl"
            items = [json.loads(l) for l in open(manifest)]
            for it in items:
                img_path = root / suite / it["image"]
                img = Image.open(img_path).convert("RGB")
                for arm, fn in ARMS.items():
                    t0 = time.perf_counter()
                    got = read_route(fn(img))
                    sec = round(time.perf_counter() - t0, 3)
                    row = {
                        "suite": suite,
                        "id": it["id"],
                        "family": it.get("family", suite),
                        "arm": arm,
                        "label": it["label"],
                        "got": got,
                        "exact": got == it["label"],
                        "sec": sec,
                    }
                    fh.write(json.dumps(row) + "\n")
                    fh.flush()
                    rows += 1
        fh.write(json.dumps({"event": "done", "rows": rows,
                             "wall_s": round(time.time() - t_start, 1)}) + "\n")
    print(f"wrote {rows} rows (+footer) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
