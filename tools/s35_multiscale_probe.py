#!/usr/bin/env python3
"""tools/s35_multiscale_probe.py — S35 (t-20261013-0a21): does multi-scale
template matching recover corroded glyphs? BOUNDED PROBE — no wiring.

Hypothesis (task spec): corrosion erosion changes glyph size, and the
shipping matcher is single-scale in effect — `baseline._cands_for_height`
only offers templates whose rendered height is within ±1 px of the crop's
height, so an eroded (shrunken) or accreted (grown) glyph falls off the
candidate window and the true character is never scored.

Variants measured (crop = the glyph mask the reader's classifier sees):
  base : baseline.match_native as shipped (height window ±1)
  tol2 : same scan, but candidate window widened to ±2 px (template-side)
  ms10 : crop rescaled ×{0.90, 1.00, 1.10} — best score across scales
  ms20 : crop rescaled ×{0.80, 0.90, 1.00, 1.10, 1.20}

Arms:
  canonical : data/hard family=corrosion items (floor-segmented pieces
              aligned to truth, the honest read-time distribution)
  corpus    : S53 corpus corrosion arm, sampled per severity — TWO crop
              sources: truth char_boxes (matcher in isolation, no
              segmentation confound) and floor pieces (read-time).

Gate: >5% relative improvement in top-1 on corroded glyphs AND latency
that keeps a full read under the 10 s bar. Report only — nothing wires in
on this task's authority.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402
import reader as R  # noqa: E402
from readers.segmentation import ink_mask  # noqa: E402

_spec = importlib.util.spec_from_file_location("cc", ROOT / "tools" / "corrosion_cnn.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)  # floor_pieces

MS10 = (0.90, 1.00, 1.10)
MS20 = (0.80, 0.90, 1.00, 1.10, 1.20)


def rescale(mask: np.ndarray, k: float) -> np.ndarray:
    if k == 1.0:
        return mask
    im = Image.fromarray((mask * 255).astype(np.uint8))
    w, h = max(1, round(im.width * k)), max(1, round(im.height * k))
    return np.array(im.resize((w, h), Image.NEAREST)) > 127


def cands(mask: np.ndarray, tol: int):
    """Candidate templates within ±tol px of the mask height (base scan)."""
    h = mask.shape[0]
    out = []
    for nominal in range(max(10, h - tol), min(72, 2 * h + 4)):
        for (ch, face), t in B._templates_native(nominal).items():
            if abs(t.shape[0] - h) <= tol:
                out.append((ch, face, t))
    return sorted(out, key=lambda cf: (abs(cf[2].shape[0] - h), cf[1]))


def scan_best(mask: np.ndarray, tol: int = 1) -> tuple[str, float]:
    """match_native's scan with a parameterised height tolerance."""
    best = ("?", -1.0)
    seen = 0
    for ch, face, t in cands(mask, tol):
        s = R._score_glyph(mask, t)
        seen += 1
        if s > best[1]:
            best = (ch, s)
            if s >= 0.997 and seen >= 24:
                break
    return best


def match_ms(mask: np.ndarray, scales) -> tuple[str, float]:
    """Best (char, score) over crop rescales — the multi-scale variant."""
    best = ("?", -1.0)
    for k in scales:
        m = rescale(mask, k)
        ch, s = scan_best(m, 1)
        if s > best[1]:
            best = (ch, s)
    return best


MATCHERS = {
    "base": lambda m: scan_best(m, 1),
    "tol2": lambda m: scan_best(m, 2),
    "ms10": lambda m: match_ms(m, MS10),
    "ms20": lambda m: match_ms(m, MS20),
}


def evaluate(crops, truths, cells, label, latency=False):
    """crops: list[mask], truths: list[char], cells: list[str] per crop."""
    res = {}
    for name, fn in MATCHERS.items():
        t0 = time.time()
        hits, tot = 0, 0
        per_cell = defaultdict(lambda: [0, 0])
        for m, ch, cell in zip(crops, truths, cells):
            got, _s = fn(m)
            hits += got == ch
            tot += 1
            per_cell[cell][0] += got == ch
            per_cell[cell][1] += 1
        dt = time.time() - t0
        res[name] = {
            "top1": round(hits / tot, 4), "n": tot,
            "ms_per_crop": round(1000 * dt / tot, 2),
            "per_cell": {k: [v[0], v[1]] for k, v in sorted(per_cell.items())},
        }
        print(f"  {label:34s} {name:5s} top1 {res[name]['top1']:.4f} "
              f"({res[name]['ms_per_crop']:.1f} ms/crop)", flush=True)
    return res


def corpus_crops(rows, corpus_dir, per_sev, source):
    crops, truths, cells = [], [], []
    by = defaultdict(list)
    for r in rows:
        if r["degradation_type"] == "corrosion":
            by[r["severity"]].append(r)
    for sev, items in sorted(by.items()):
        for r in items[:per_sev]:
            img = Image.open(corpus_dir / r["image"])
            glyphs = [c for c in r["label"] if c != " "]
            if source == "truth":
                mask = ink_mask(img)
                H, W = mask.shape
                for ch, b in zip(glyphs, r["char_boxes"]):
                    x0, x1, y0, y1 = b
                    crop = mask[max(0, y0):min(H, y1 + 1), max(0, x0):min(W, x1 + 1)]
                    if crop.any():
                        crops.append(crop)
                        truths.append(ch)
                        cells.append(f"corpus/{sev}")
            else:  # floor
                _, pieces, _ = cc.floor_pieces(img)
                if len(pieces) == len(glyphs):
                    for ch, p in zip(glyphs, pieces):
                        crops.append(p.astype(bool))
                        truths.append(ch)
                        cells.append(f"corpus/{sev}")
    return crops, truths, cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/hard2000")
    ap.add_argument("--per-sev", type=int, default=30)
    ap.add_argument("--out", default="reports/s35-multiscale/probe.json")
    args = ap.parse_args()
    out = {}

    # --- generated canonical-recipe corrosion (floor pieces, read-time
    # distribution). The seed-1 suite's 8 corrosion items align almost
    # never (segmentation owns the misses), so probe on FRESH seed-71
    # renders — same fam_corrosion recipe, no eval-suite contamination.
    import generator as G  # noqa: E402
    crops, truths, cells = [], [], []
    for i in range(40):
        img, label = G.generate_one("corrosion", seed=71, index=i)
        _, pieces, _ = cc.floor_pieces(img)
        glyphs = [c for c in label if c != " "]
        if len(pieces) == len(glyphs):
            for ch, p in zip(glyphs, pieces):
                crops.append(p.astype(bool))
                truths.append(ch)
                cells.append("generated/corrosion")
    print(f"generated corrosion (seed 71): {len(crops)} aligned floor crops", flush=True)
    out["generated_floor"] = evaluate(crops, truths, cells, "generated/corrosion (floor)")

    # --- corpus corrosion arm
    corpus_dir = Path(args.corpus)
    rows = [json.loads(l) for l in open(corpus_dir / "manifest.jsonl")]
    for source in ("truth", "floor"):
        crops, truths, cells = corpus_crops(rows, corpus_dir, args.per_sev, source)
        print(f"corpus corrosion [{source}]: {len(crops)} crops", flush=True)
        if crops:
            out[f"corpus_{source}"] = evaluate(crops, truths, cells,
                                               f"corpus corrosion ({source})")

    # --- latency context: shipping read cost on generated corrosion
    t0 = time.time()
    n_reads = 0
    for i in range(8):
        img, _label = G.generate_one("corrosion", seed=71, index=i)
        B.read_text(img)
        n_reads += 1
    per_read = (time.time() - t0) / max(1, n_reads)
    print(f"\nshipping read_text on canonical corrosion: {per_read:.2f} s/read "
          f"({n_reads} reads)", flush=True)
    out["shipping_read_s"] = round(per_read, 2)

    # --- verdict against the >5% gate
    gate = {}
    for arm in out:
        if not isinstance(out[arm], dict) or "base" not in out[arm]:
            continue
        base = out[arm]["base"]["top1"]
        for name in ("tol2", "ms10", "ms20"):
            v = out[arm][name]["top1"]
            rel = (v - base) / base if base else 0.0
            gate[f"{arm}/{name}"] = {
                "base": base, "variant": v,
                "rel_improvement": round(rel, 4),
                "passes_5pct_gate": rel > 0.05,
            }
    out["gate"] = gate
    print("\n--- gate (>5% relative top-1 improvement on corroded glyphs) ---")
    for k, v in gate.items():
        print(f"  {k:34s} {v['base']:.4f} -> {v['variant']:.4f} "
              f"({v['rel_improvement']*100:+.1f}%) {'PASS' if v['passes_5pct_gate'] else 'fail'}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"\nreport {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
