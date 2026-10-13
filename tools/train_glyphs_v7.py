#!/usr/bin/env python3
"""tools/train_glyphs_v7.py — S30 iteration 3 (t-20261013-6d08): fine-tune
glyphcnn on the S53 hard-corpus word-context crops.

Lineage: v5 (de-rotation-aware augs) failed the staged bar and v6
(synthetic word-context rendering) was lost before its first run — but the
v6 postmortem stands: solo-glyph training never sees read-time crop
semantics, because textlength advance boxes include 1-2 px of neighbour
ink and every adjacent pair overlaps after rotation. The S53 corpus
(2000 severity-controlled items, PR #66) carries per-char TRUTH boxes on
already-degraded sheets, so v7 trains on exactly what the reader's
classifier sees at read time: ink-mask crops cut at truth boxes ± 1 px of
word context, degradation included.

Held-out protocol (binding, per reports/s53-hard-corpus/report.md):
  - canonical suites (seed 1/2) NEVER enter training;
  - the seed-53 corpus is split BY ITEM INDEX: 0-1599 train, 1600-1999
    validation — stratified ~80/20 per arm (verified);
  - the receipt reports per-severity val accuracy on the held-out 400,
    v4-baseline vs v7, per arm.

    python3 tools/train_glyphs_v7.py --corpus /path/to/corpus/hard2000 \
        --epochs 10 --out models/glyphcnn-v7.npz
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from readers.glyphcnn import GlyphCNN, char_to_index  # noqa: E402
from readers.segmentation import ink_mask, normalise_glyph  # noqa: E402
from readers.glyphcnn import write_recipe  # noqa: E402

CONTEXT_PX = 1  # word-context: truth box expanded by this many px per side

_cc_mod = None


def _cc():
    """tools/corrosion_cnn.py (floor_pieces) — lazy to avoid import cycles."""
    global _cc_mod
    if _cc_mod is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cc", ROOT / "tools" / "corrosion_cnn.py")
        _cc_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_cc_mod)
    return _cc_mod


def harvest(rows: list[dict], corpus_dir: Path, tag: str, modes=("word",), ctx=None):
    """(x, y, cell) crops from corpus items, one crop per mode per glyph.

    word : truth advance-box ± CONTEXT_PX (neighbour ink included — read-time
           semantics for a word-context-cropping reader)
    tight: the floor's own segmented pieces aligned to truth chars (the
           distribution corrosion_cnn/read_with_net feed the net at read time)
    """
    xs, ys, cells, skipped = [], [], [], 0
    for r in rows:
        label = r["label"]
        glyphs = [c for c in label if c != " "]
        boxes = r["char_boxes"]
        if len(glyphs) != len(boxes):
            skipped += 1
            continue
        img = Image.open(corpus_dir / r["image"])
        mask = ink_mask(img)
        H, W = mask.shape
        cell = f"{r['degradation_type']}/{r['severity']}"
        c = CONTEXT_PX if ctx is None else ctx
        if "word" in modes:
            for ch, b in zip(glyphs, boxes):
                x0, x1, y0, y1 = b            # corpus order: x0, x1, y0, y1
                X0, X1 = max(0, x0 - c), min(W - 1, x1 + c)
                Y0, Y1 = max(0, y0 - c), min(H - 1, y1 + c)
                xs.append(normalise_glyph(mask, (X0, Y0, X1, Y1)))
                ys.append(char_to_index(ch))
                cells.append(cell)
        if "tight" in modes:
            _, pieces, _ = _cc().floor_pieces(img)
            if len(pieces) != len(glyphs):
                skipped += 1
            else:
                for ch, p in zip(glyphs, pieces):
                    h, w = p.shape
                    xs.append(normalise_glyph(p.astype(bool), (0, 0, w - 1, h - 1)))
                    ys.append(char_to_index(ch))
                    cells.append(cell)
    x = np.stack(xs).astype(np.float32)[:, None, :, :]  # (N, 1, 24, 24) NCHW
    y = np.array(ys, dtype=np.int64)
    print(f"{tag} [{'+'.join(modes)}]: {len(x)} crops from {len(rows)} items "
          f"({skipped} skips)", flush=True)
    return x, y, cells, skipped


def _class_indices(y):
    by = defaultdict(list)
    for i, c in enumerate(y.tolist()):
        by[c].append(i)
    return by


def chunked_predict(model, x, chunk: int = 1024) -> np.ndarray:
    """predict in slices — one im2col over the whole val set OOMs (RC=137)."""
    return np.concatenate([model.predict(x[i:i + chunk])
                           for i in range(0, len(x), chunk)])


def per_cell(model, x, y, cells, name):
    """Per-severity top-1 accuracy table (aggregating combined-* picks)."""
    by = defaultdict(lambda: [0, 0])
    preds = chunked_predict(model, x)
    ok = preds == y
    for i, c in enumerate(cells):
        key = "combined/mixed" if c.startswith("combined") else c
        by[key][0] += int(ok[i])
        by[key][1] += 1
    table = {k: {"acc": round(v[0] / v[1], 4), "n": v[1]}
             for k, v in sorted(by.items())}
    print(f"\n--- {name} per-severity (crop-level top-1) ---", flush=True)
    for k, v in table.items():
        print(f"  {k:26s} {v['acc']:.4f}  (n={v['n']})", flush=True)
    print(f"  {'TOTAL':26s} {float(ok.mean()):.4f}  (n={len(y)})", flush=True)
    return table, float(ok.mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus/hard2000")
    ap.add_argument("--init", default="models/glyphcnn-v4.npz")
    ap.add_argument("--out", default="models/glyphcnn-v7.npz")
    ap.add_argument("--train-n", type=int, default=1600)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--lr-end", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--cap", type=int, default=800)
    ap.add_argument("--context-px", type=int, default=None,
                    help="word-mode context px (default: module CONTEXT_PX=1)")
    ap.add_argument("--modes", default="word",
                    help="comma list: word,tight")
    ap.add_argument("--report", default="reports/s30-v7/per-severity.json")
    args = ap.parse_args()

    corpus_dir = Path(args.corpus)
    rows = [json.loads(l) for l in open(corpus_dir / "manifest.jsonl")]
    assert len(rows) >= args.train_n + 1, "corpus too small for the split"
    train_rows, val_rows = rows[:args.train_n], rows[args.train_n:]
    print(f"corpus {corpus_dir}: {len(rows)} items -> "
          f"train {len(train_rows)} / val {len(val_rows)} (held-out by index, "
          f"per reports/s53-hard-corpus/report.md)", flush=True)

    t0 = time.time()
    modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
    xtr, ytr, _, sk_tr = harvest(train_rows, corpus_dir, "train", modes, args.context_px)
    xva, yva, cva, sk_va = harvest(val_rows, corpus_dir, "val", modes, args.context_px)
    counts = Counter(ytr)
    print(f"harvest {time.time() - t0:.1f}s; class counts train min/max: "
          f"{min(counts.values())}/{max(counts.values())}", flush=True)

    # cap frequent classes (corpus labels are natural words -> 11..2897 per
    # class); rare classes keep everything. Deterministic per-seed subsample.
    if args.cap:
        rng = np.random.default_rng(args.seed)
        keep = []
        for cls, idxs in _class_indices(ytr).items():
            idxs = np.array(idxs)
            if len(idxs) > args.cap:
                idxs = rng.choice(idxs, size=args.cap, replace=False)
            keep.extend(idxs.tolist())
        keep = np.array(sorted(keep))
        xtr, ytr = xtr[keep], ytr[keep]
        counts = Counter(ytr.tolist())
        print(f"capped at {args.cap}/class -> {len(xtr)} train crops, "
              f"class min/max {min(counts.values())}/{max(counts.values())}",
              flush=True)

    # fit's per-epoch val uses a fixed 2000-crop subsample (its predict is
    # unchunked); the receipt uses the full val through chunked_predict.
    rng = np.random.default_rng(args.seed + 1)
    fit_idx = np.sort(rng.choice(len(xva), size=min(2000, len(xva)),
                                 replace=False))
    xva_fit, yva_fit = xva[fit_idx], yva[fit_idx]

    model = GlyphCNN.load(args.init)
    base_table, base_total = per_cell(model, xva, yva, cva, f"baseline {args.init}")

    print(f"\nfine-tuning: epochs {args.epochs}, batch {args.batch}, "
          f"lr {args.lr} -> {args.lr_end}, seed {args.seed}", flush=True)
    t0 = time.time()
    hist = model.fit(xtr, ytr, xva_fit, yva_fit, epochs=args.epochs, batch=args.batch,
                     lr=args.lr, lr_end=args.lr_end, seed=args.seed, verbose=True)
    print(f"fit {time.time() - t0:.1f}s", flush=True)

    v7_table, v7_total = per_cell(model, xva, yva, cva, "v7")

    model.save(args.out)
    info = {
        "task": "t-20261013-6d08 (S30 v7)",
        "init": args.init,
        "corpus": "S53 hard corpus, seed 53, manifest sha256 44b79be7ea90551a",
        "protocol": "held-out by item index: train 0-1599, val 1600-1999; "
                    "canonical suites never trained on",
        "crops": {"train": len(xtr), "val": len(xva),
                  "skipped_items": sk_tr + sk_va},
        "context_px": args.context_px if args.context_px is not None else CONTEXT_PX,
        "crop_modes": list(modes),
        "train_cap_per_class": args.cap,
        "epochs": args.epochs, "batch": args.batch,
        "lr": args.lr, "lr_end": args.lr_end, "seed": args.seed,
        "history": [(e, round(l, 4), None if a is None else round(a, 4))
                    for e, l, a in hist],
        "baseline_val_total": round(base_total, 4),
        "v7_val_total": round(v7_total, 4),
        "baseline_per_cell": base_table,
        "v7_per_cell": v7_table,
    }
    write_recipe(args.out, info)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    json.dump(info, open(args.report, "w"), indent=1)
    print(f"\nsaved {args.out}; recipe written; report {args.report}", flush=True)
    print(f"VAL_TOTAL base {base_total:.4f} -> v7 {v7_total:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
