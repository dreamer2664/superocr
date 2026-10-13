#!/usr/bin/env python3
"""s52_contour_probe.py — S52 (t-20261013-7c60): contour features for
glyph disambiguation, measured — NOT wired.

Premise under test: pixel-template matching confuses similar glyphs, and
stroke-width / curvature / aspect features could re-rank them.

Honest framing after S35/S50: the read-level confusion surface is small
(S43: 5 glyph-substitution misses on hard; easy's residue mixes case and
glyph swaps). So the probe measures, in order:

  1. INVENTORY (score level, both suites): for every floor-aligned
     glyph, the template scan's winner vs truth — split misses into
     rank-errors (truth in top-8, rerankable) vs absent-truth (stroke
     destroyed / segmentation, not rerankable).
  2. FEATURES: per glyph mask — stroke width (median ink distance-to-
     edge x2), compactness (perimeter^2/area), aspect, hole count
     (Euler), ink density. Cheap, deterministic, no skeletons.
  3. OFFLINE DISCRIMINABILITY: on corpus truth-box crops (real10k), do
     the features separate the template scorer's actual confusion pairs?
     Nearest-centroid classifier on features alone, per confusion pair.
  4. RERANK SIMULATION (read level): where the template winner's margin
     is thin AND a feature classifier disagrees, swap in the feature
     choice; count exact-match fixes vs breaks on both suites.

Gate: >5% exact-match improvement on hard with zero easy regression to
even propose wiring.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import baseline as B  # noqa: E402
import reader as R  # noqa: E402

_spec = importlib.util.spec_from_file_location("cc", ROOT / "tools" / "corrosion_cnn.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)  # floor_pieces


# ------------------------------------------------------------------ features
def contour_features(mask: np.ndarray) -> dict | None:
    """Stroke width, compactness, aspect, holes, density for a bool mask."""
    if mask.sum() < 12:
        return None
    h, w = mask.shape
    ink = mask.astype(np.uint8)
    # distance to nearest zero — stroke width proxy (2x median of interior)
    from collections import deque
    INF = 1 << 20
    dist = np.full((h, w), INF, dtype=np.int32)
    dq = deque()
    for y in range(h):
        for x in range(w):
            if not ink[y, x]:
                dist[y, x] = 0
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        d = dist[y, x] + 1
        for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
            if 0 <= ny < h and 0 <= nx < w and dist[ny, nx] > d:
                dist[ny, nx] = d
                dq.append((ny, nx))
    ink_d = dist[mask]
    sw = float(np.median(ink_d)) * 2.0
    # perimeter: ink pixels adjacent to non-ink (4-neighbour)
    pad = np.pad(ink, 1)
    peri = int((pad[1:-1,1:-1] & ~(pad[:-2,1:-1] & pad[2:,1:-1] &
                                   pad[1:-1,:-2] & pad[1:-1,2:])).sum())
    area = int(ink.sum())
    compact = (peri * peri) / area if area else 0.0
    # holes: connected background components not touching the border
    bg = ~ink
    visited = np.zeros_like(bg)
    holes = 0
    for y in range(h):
        for x in range(w):
            if bg[y, x] and not visited[y, x]:
                stack = [(y, x)]
                visited[y, x] = True
                touches = (y == 0 or y == h-1 or x == 0 or x == w-1)
                comp = 0
                while stack:
                    cy, cx = stack.pop()
                    comp += 1
                    for ny, nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
                        if 0 <= ny < h and 0 <= nx < w and bg[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            if ny in (0, h-1) or nx in (0, w-1):
                                touches = True
                            stack.append((ny, nx))
                if not touches and comp >= 3:
                    holes += 1
    return {
        "stroke_w": sw,
        "compact": compact,
        "aspect": w / h,
        "holes": holes,
        "density": area / (w * h),
        "fill_ratio": area / max(1, (mask.any(axis=1).sum() * mask.any(axis=0).sum())),
    }


FEATURE_ORDER = ("stroke_w", "compact", "aspect", "holes", "density", "fill_ratio")


def feat_vec(f: dict) -> np.ndarray:
    return np.array([f[k] for k in FEATURE_ORDER], dtype=np.float64)


# ------------------------------------------------------------------ probe
def inventory(split: str):
    """Floor-aligned glyphs with template scan results vs truth."""
    rows = [json.loads(l) for l in open(f"data/{split}/manifest.jsonl")]
    recs = []
    for r in rows:
        img = Image.open(Path("data") / split / r["image"])
        _, pieces, _ = cc.floor_pieces(img)
        glyphs = [c for c in r["label"] if c != " "]
        if len(pieces) != len(glyphs):
            continue
        for ch, p in zip(glyphs, pieces):
            top = B._scan_native(p.astype(bool), k=8)
            winner = top[0][0] if top else "?"
            truth_rank = next((i for i, (c, s) in enumerate(top) if c == ch), -1)
            margin = (top[0][1] - top[1][1]) if len(top) > 1 else 1.0
            recs.append({"glyph": ch, "winner": winner, "correct": winner == ch,
                         "truth_rank": truth_rank, "margin": round(margin, 4),
                         "piece": p})
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/real10k")
    ap.add_argument("--corpus-n", type=int, default=3000)
    ap.add_argument("--out", default="reports/s52-contour/probe.json")
    args = ap.parse_args()
    report = {}

    # ---- 1. inventory on both suites
    for split in ("hard", "easy"):
        recs = inventory(split)
        wrong = [r for r in recs if not r["correct"]]
        rank_err = [r for r in wrong if r["truth_rank"] > 0]
        absent = [r for r in wrong if r["truth_rank"] < 0]
        pairs = Counter(f"{r['winner']}->{r['glyph']}" for r in wrong)
        print(f"{split}: {len(recs)} aligned glyphs | wrong {len(wrong)} "
              f"(rank-errors {len(rank_err)}, truth-absent {len(absent)})", flush=True)
        print(f"  top confusions: {pairs.most_common(10)}", flush=True)
        report[f"{split}_inventory"] = {
            "aligned": len(recs), "wrong": len(wrong),
            "rank_errors": len(rank_err), "truth_absent": len(absent),
            "confusions": dict(pairs.most_common(20)),
        }
        report[f"{split}_inventory"]["rank_err_pairs"] = dict(
            Counter(f"{r['winner']}->{r['glyph']}" for r in rank_err).most_common(20))

    # ---- 2+3. feature discriminability on corpus truth crops
    rows = [json.loads(l) for l in open(Path(args.corpus) / "manifest.jsonl")]
    import random
    rng = random.Random(7)
    cleanish = [r for r in rows if r["degradation_type"] in
                ("control", "paperdegrade", "perspective")][: args.corpus_n]
    rng.shuffle(cleanish)
    X, Y = [], []
    from readers.segmentation import ink_mask
    for r in cleanish[: args.corpus_n]:
        img = Image.open(Path(args.corpus) / r["image"])
        mask = ink_mask(img)
        H, W = mask.shape
        for ch, b in zip([c for c in r["label"] if c != " "], r["char_boxes"]):
            x0, x1, y0, y1 = max(0, b[0]), min(W, b[1]), max(0, b[2]), min(H, b[3])
            crop = mask[y0:y1 + 1, x0:x1 + 1]
            f = contour_features(crop)
            if f:
                X.append(feat_vec(f))
                Y.append(ch)
    X = np.array(X)
    print(f"\ncorpus feature crops: {len(X)} glyphs, {len(set(Y))} classes", flush=True)

    # normalise
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    Xn = (X - mu) / sd
    # nearest-centroid classifier
    cents = {}
    for c in sorted(set(Y)):
        cents[c] = Xn[np.array(Y) == c].mean(axis=0)
    pred = []
    for x in Xn:
        best, bd = "?", 1e18
        for c, m in cents.items():
            d = float(((x - m) ** 2).sum())
            if d < bd:
                best, bd = c, d
        pred.append(best)
    acc = sum(p == y for p, y in zip(pred, Y)) / len(Y)
    print(f"features-alone nearest-centroid accuracy: {acc:.4f}", flush=True)
    report["feature_nc_accuracy"] = round(acc, 4)
    report["feature_crops"] = len(X)

    # per-pair discriminability for the template lane's actual confusions
    conf_pairs = set()
    for split in ("hard", "easy"):
        conf_pairs |= set(report[f"{split}_inventory"]["rank_err_pairs"])
    pair_scores = {}
    for pair in list(conf_pairs)[:12]:
        w, t = pair.split("->")
        sel = [i for i, y in enumerate(Y) if y in (w, t)]
        if len(sel) < 20:
            continue
        sub_pred = [pred[i] for i in sel]
        sub_y = [Y[i] for i in sel]
        pair_acc = sum(p == y for p, y in zip(sub_pred, sub_y)) / len(sel)
        base = max(sum(1 for y in sub_y if y == w), sum(1 for y in sub_y if y == t)) / len(sel)
        pair_scores[pair] = {"n": len(sel), "feature_acc": round(pair_acc, 3),
                             "majority_baseline": round(base, 3)}
        print(f"  pair {pair}: feature acc {pair_acc:.3f} vs majority {base:.3f} (n={len(sel)})",
              flush=True)
    report["pair_discriminability"] = pair_scores

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(args.out, "w"), indent=1)
    print(f"\nreport {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
