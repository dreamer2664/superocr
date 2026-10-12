#!/usr/bin/env python3
"""s12_confusion.py — the router's honest picture on the OFFICIAL suites (t-20261012-30bf).

Not a held-out generator sample: the actual bench suites (data/easy,
data/hard, seed 1, hash b2c460d2fb5a — the same images every official number
is measured on). Ground truth is the manifest's family field; the router has
never seen seed-1 images (the centroids are seed 42, indices 200-207).

Prints the full 13x13 confusion matrix plus per-family top-1, and the number
that matters most for S12: how often each WALL family (the four with S7c
masks: cross-shadow, darts, corrosion, dark-on-dark) is reached by routing,
and how often non-wall images are MIS-routed into a wall family (the only
way auto can do worse than plain).

Usage:
    python3 tools/s12_confusion.py                # both suites
    python3 tools/s12_confusion.py --suite hard
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import preclassify as P  # noqa: E402

WALL = ("cross-shadow", "darts", "corrosion", "dark-on-dark")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="easy,hard", help="comma list: easy,hard")
    ap.add_argument("--data", default=str(ROOT / "data"), help="suite root")
    a = ap.parse_args(argv)

    fams = P.ALL_FAMILIES
    n_wrong_into_wall = Counter()
    for suite in a.suite.split(","):
        man = Path(a.data) / suite / "manifest.jsonl"
        if not man.exists():
            print(f"suite '{suite}' not built ({man} missing) — "
                  "run: python3 tools/make_suites.py", file=sys.stderr)
            return 2
        rows = [json.loads(l) for l in man.read_text().splitlines() if l.strip()]
        conf = {f: Counter() for f in fams}
        for r in rows:
            img = Image.open(Path(a.data) / suite / r["image"])
            conf[r["family"]][P.rank(img)[0]] += 1
        print(f"\n=== suite '{suite}' — {len(rows)} images, "
              f"rows=true family, columns=routed family ===")
        print(" " * 14 + "".join(f"{f[:6]:>8}" for f in fams) + "   top1")
        for f in fams:
            cells = "".join(f"{conf[f].get(g, 0) if g == f else ('.' if not conf[f].get(g) else conf[f][g]):>8}"
                            for g in fams)
            hit = conf[f].get(f, 0)
            print(f"{f:14s}{cells}   {hit}/{sum(conf[f].values())}")
        tot = sum(sum(conf[f].values()) for f in fams)
        hits = sum(conf[f].get(f, 0) for f in fams)
        print(f"top-1 total: {hits}/{tot} = {hits / tot:.0%}")
        wrong_wall = sum(conf[f][w] for f in fams if f not in WALL for w in WALL)
        wall_missed = sum(conf[w][g] for w in WALL for g in fams if g != w)
        print(f"wall families: routed-right "
              f"{sum(conf[w].get(w, 0) for w in WALL)}/{sum(sum(conf[w].values()) for w in WALL)}"
              f"; wall MISSED (mask not applied): {wall_missed}")
        print(f"non-wall MIS-ROUTED INTO a wall family (wrong mask applied): {wrong_wall}")
        n_wrong_into_wall[suite] = wrong_wall
    return 0


if __name__ == "__main__":
    sys.exit(main())
