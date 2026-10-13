#!/usr/bin/env python3
"""tools/s30_v7_read_probe.py — S30 v7 read-level receipt (t-20261013-6d08).

v7 (fine-tuned on S53-corpus word-context crops) vs its init (glyphcnn-v4)
through the FLOOR's own segmentation (autocontrast -> otsu -> despeck ->
trim -> segment -> split_wide), net as classifier — the same flow
corrosion_cnn.py measures with. Canonical suites are EVAL-ONLY here
(seed 1; never trained on — the binding held-out protocol).

This is deliberately the SOLO-piece distribution: the floor trims each
piece tight, so it has no word context. It is v4's home turf and the
clean-collapse guard (staged bar: no clean-val collapse below 0.90), and
it tells us whether the v7 word-context gains survive integration as-is
or need a context-cropping reader change first.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402,F401  (floor_pieces pulls it)
import reader as R  # noqa: E402,F401
from readers.glyphcnn import GlyphCNN  # noqa: E402

_spec = importlib.util.spec_from_file_location("cc", ROOT / "tools" / "corrosion_cnn.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)  # floor_pieces / read_with_net / _char_acc


def probe(manifest_path: Path, nets: dict[str, GlyphCNN]):
    rows = [json.loads(l) for l in open(manifest_path)]
    per_net = {name: {"exact": 0, "char": 0.0, "items": 0} for name in nets}
    per_fam = defaultdict(lambda: {n: [0, 0] for n in nets})  # fam -> net -> [exact, n]
    glyph_hits = {n: [0, 0] for n in nets}
    for r in rows:
        img = Image.open(manifest_path.parent / r["image"])
        fam = r.get("family", "?")
        for name, net in nets.items():
            text = cc.read_with_net(img, net)
            per_net[name]["items"] += 1
            ex = text == r["label"]
            per_net[name]["exact"] += int(ex)
            per_net[name]["char"] += cc._char_acc(r["label"], text)
            per_fam[fam][name][0] += int(ex)
            per_fam[fam][name][1] += 1
        # glyph-level on aligned items (same honesty filter as corrosion_cnn)
        _, pieces, _ = cc.floor_pieces(img)
        true = [c for c in r["label"] if c != " "]
        if len(pieces) == len(true):
            import numpy as np
            from readers.glyphcnn import char_to_index
            crops = np.stack([cc.crop_of(p)[0] for p in pieces])
            probs = {n: net.forward(crops[:, None, :, :].astype(net.p["w1"].dtype))[0]
                     for n, net in nets.items()}
            for j, ch in enumerate(true):
                yi = char_to_index(ch)
                for n in nets:
                    glyph_hits[n][0] += int(int(probs[n][j].argmax()) == yi)
                    glyph_hits[n][1] += 1
    return per_net, per_fam, glyph_hits, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests", nargs="+",
                    default=["data/easy/manifest.jsonl", "data/hard/manifest.jsonl"])
    ap.add_argument("--baseline", default="models/glyphcnn-v4.npz")
    ap.add_argument("--weights", default="models/glyphcnn-v7.npz")
    ap.add_argument("--out", default="reports/s30-v7/read-probe.json")
    args = ap.parse_args()

    nets = {"v4": GlyphCNN.load(args.baseline), "v7": GlyphCNN.load(args.weights)}
    out = {"baseline": args.baseline, "weights": args.weights, "manifests": {}}
    for m in args.manifests:
        t0 = time.time()
        per_net, per_fam, glyph_hits, n = probe(Path(m), nets)
        print(f"\n=== {m} ({n} items, {time.time() - t0:.0f}s) ===", flush=True)
        for name, s in per_net.items():
            print(f"  {name}: exact {s['exact']}/{n} = {s['exact']/n:.3f} | "
                  f"mean char-acc {s['char']/n:.3f}", flush=True)
        for name, (h, t) in glyph_hits.items():
            print(f"  {name}: glyph acc (aligned) {h}/{t} = {h/t:.4f}", flush=True)
        fam_tab = {f: {n: f"{v[0]}/{v[1]}" for n, v in d.items()}
                   for f, d in sorted(per_fam.items())}
        for f, d in sorted(per_fam.items()):
            print(f"    {f:14s} v4 {d['v4'][0]:2d}/{d['v4'][1]:<3d}  "
                  f"v7 {d['v7'][0]:2d}/{d['v7'][1]:<3d}", flush=True)
        out["manifests"][m] = {
            "n": n,
            "per_net": per_net,
            "glyph": {n: {"acc": round(h / t, 4), "n": t} for n, (h, t) in glyph_hits.items()},
            "per_family": fam_tab,
        }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"\nreport {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
