#!/usr/bin/env python3
"""tools/ensemble_select.py — S6 phase 1: combine readers (t-20261011-00c0).

Before building any ensemble MECHANISM, measure what "best chain per family"
would score with the readers we already have. Three chains, one bench-style
measurement loop, same seeds everywhere:

    classic   the honest floor (baseline.read_text, family-agnostic)
    strategy  main reader.py's family dispatcher (read_chain)
    cnn       scott's glyph CNN (readers/, weights committed)

    python3 tools/ensemble_select.py --count 10 --seed 7 \
        --out reports/ensemble-select.json

The per-family winner table IS the report: where the combine adds exact
matches and where NOTHING helps (the honest rows stay in). The selector
mechanism itself is a later task; this ships only what it can prove.

Needs: bench is NOT required (this measures; bench judges). CNN is optional
in the tree — if readers/ is absent the cnn chain is skipped and the report
says why.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import baseline as B  # noqa: E402
import generator as G  # noqa: E402
import reader as R  # noqa: E402

CNN_OK = True
try:
    from readers.glyphcnn import GlyphCNN  # noqa: E402
    from readers.segmentation import analyse, normalise_glyph  # noqa: E402
except Exception:  # pragma: no cover - cnn branch missing
    CNN_OK = False


def _char_acc(label: str, text: str) -> float:
    l1, l2 = label.replace(" ", ""), text.replace(" ", "")
    if not l1 and not l2:
        return 1.0
    tot = max(len(l1), len(l2))
    return sum(a == b for a, b in zip(l1, l2)) / tot if tot else 0.0


def classic_read(img, _net=None, **_):
    return B.read_text(img)[0]


def strategy_read(img, network=None, family=""):
    return R.read_chain(img, family)[0]


def cnn_read(img, network, **_):
    from PIL import Image
    from readers.glyphcnn import index_to_char  # noqa:  # local, tiny
    mask, boxes = analyse(img.convert("RGB"))
    if not boxes:
        return ""
    crops = np.stack([normalise_glyph(mask, box) for box, _ in boxes])[:, None, :, :]
    probs = network.forward(crops.astype(network.p["w1"].dtype))[0]
    out = []
    for i, (_, space_before) in enumerate(boxes):
        ch = index_to_char(int(probs[i].argmax()))
        if space_before and out and out[-1] != " ":
            out.append(" ")
        out.append(ch)
    return "".join(out)


CHAINS = [("classic", classic_read), ("strategy", strategy_read)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--families", default="")
    ap.add_argument("--eval-seed", type=int, default=0,
                    help="held-out seed: the per-family winner is FROZEN from "
                         "the selection seed and only then scored here (fixes "
                         "winner's-curse reporting: select on 7, eval on 3)")
    ap.add_argument("--out", help="json report path")
    args = ap.parse_args()

    chains = list(CHAINS)
    net = None
    if CNN_OK:
        weights = ROOT / "models" / "glyphcnn.npz"
        if weights.exists():
            net = GlyphCNN.load(str(weights))
            chains.append(("cnn", cnn_read))
        else:
            print("cnn chain skipped: no weights at models/glyphcnn.npz") 
    else:
        print("cnn chain skipped: readers/ not in this tree")

    fams = [f for f in args.families.split(",") if f] or list(G.FAMILIES)
    per_family: list[dict] = []
    t0 = time.time()
    table = {}
    for fam in fams:
        rows = {}
        for chain_name, fn in chains:
            exact = cok = 0
            msd = []
            for i in range(count := args.count):
                img, label = G.generate_one(fam, seed=args.seed, index=i)
                st = time.time()
                text = fn(img, network=net, family=fam)
                msd.append(time.time() - st)
                exact += text == label
                cok += _char_acc(label, text)
            rows[chain_name] = {"exact": round(exact / count, 4),
                                "char": round(cok / count, 4),
                                "median_s": round(sorted(msd)[len(msd) // 2], 3)}
        # winner: best exact, tie -> better char, then strategy (prior shipped)
        win = max(rows, key=lambda c: (rows[c]["exact"], rows[c]["char"]))
        per_family.append({"family": fam, "winner": win, "chains": rows})
        table[fam] = win

    exact_best = exact_flat = n = 0
    char_best = char_flat = 0.0
    for row in per_family:
        best_c = row["chains"][row["winner"]]
        exact_best += best_c["exact"] * args.count
        char_best += best_c["char"] * args.count
        n += args.count
    report = {
        "seed": args.seed, "count": args.count, "chains": [c for c, _ in chains],
        "best_of_combined": {"exact": round(exact_best / n, 4), "char": round(char_best / n, 4)},
        "per_family": per_family,
        "seconds": round(time.time() - t0, 1),
    }

    if args.eval_seed:
        held = []
        ho_sum = cl_sum = 0.0
        for row in per_family:
            fam, chain_name = row["family"], row["winner"]
            fn = dict(chains)[chain_name]
            exact = cok = 0
            for i in range(args.count):
                img, label = G.generate_one(fam, seed=args.eval_seed, index=i)
                text = fn(img, network=net, family=fam)
                exact += text == label
                cok += _char_acc(label, text)
            held.append({"family": fam, "chain_used": chain_name,
                         "exact": round(exact / args.count, 4),
                         "char": round(cok / args.count, 4)})
            ho_sum += exact
        cl_fn = dict(chains)["classic"]
        for fam in [r["family"] for r in per_family]:
            exact = 0
            for i in range(args.count):
                img, label = G.generate_one(fam, seed=args.eval_seed, index=i)
                exact += cl_fn(img) == label
            cl_sum += exact
        report["held_out"] = {
            "eval_seed": args.eval_seed,
            "frozen_combined_exact": round(ho_sum / n, 4),
            "classic_alone_exact": round(cl_sum / n, 4),
            "gain_over_classic_points": round((ho_sum - cl_sum) / n * 100, 1),
            "per_family": held,
        }
        report["seconds"] = round(time.time() - t0, 1)

    print(f"ensemble select — {args.count} image(s)/family, seed {args.seed}, "
          f"{len(chains)} chains, {report['seconds']}s")
    print(f"  best-of-combined: exact {report['best_of_combined']['exact']*100:.1f}%  "
          f"char {report['best_of_combined']['char']*100:.1f}%")
    if "held_out" in report:
        h = report["held_out"]
        print(f"  HELD-OUT seed {h['eval_seed']} (winners frozen from seed {args.seed}): "
              f"frozen {h['frozen_combined_exact']*100:.1f}% vs classic-alone "
              f"{h['classic_alone_exact']*100:.1f}% -> {h['gain_over_classic_points']:+.1f} points")
    print("  per family (selection seed):")
    for row in per_family:
        cells = "  ".join(f"{c}={row['chains'][c]['exact']*100:.0f}%" for c, _ in chains)
        print(f"    {row['family']:<14} {cells}  -> {row['winner']}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"report written: {args.out}")


if __name__ == "__main__":
    main()
