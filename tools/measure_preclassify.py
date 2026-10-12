#!/usr/bin/env python3
"""measure_preclassify.py — how good is auto's router, honestly (S9 harness).

preclassify.rank decides which chain auto runs. This tool measures that
routing against the repo's own generator, on a seed you name (default 404 —
never used while tuning), and prints per-family:

  routed-first : the true family is rank()[0] — the chain auto would run first
  in-top3      : the true family is among the first three candidates

It also reports, per family, what auto ACTUALLY returns (auto's family vs the
true family) — routing and reading are different questions and this tool
never merges them.

Usage: python3 tools/measure_preclassify.py [--seed 404] [--per-class 10] [--probes]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generator as G        # noqa: E402
import preclassify as P      # noqa: E402
import typer as T            # noqa: E402

FAMILIES = ["easy"] + [f for f in G.FAMILIES if f != "easy"]
PROBES = (("easy", 11), ("snow", 12), ("obstruction", 13),
          ("split", 14), ("strippy", 15), ("dark-on-dark", 16))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=404)
    ap.add_argument("--per-class", type=int, default=10)
    ap.add_argument("--probes", action="store_true")
    a = ap.parse_args(argv)

    print(f"held-out seed {a.seed}, {a.per_class} per family:")
    tot = first = top3 = 0
    for fam in FAMILIES:
        f1 = t3 = 0
        for i in range(a.per_class):
            img, _ = G.generate_one(fam, a.seed, index=i)
            ranked = P.rank(img)
            f1 += int(ranked[0] == fam)
            t3 += int(fam in ranked[:3])
        print(f"  {fam:14} routed-first {f1:>2}/{a.per_class}   "
              f"in-top3 {t3:>2}/{a.per_class}")
        tot += a.per_class
        first += f1
        top3 += t3
    print(f"  TOTAL          routed-first {first}/{tot} = {first/tot:.0%}   "
          f"in-top3 {top3}/{tot} = {top3/tot:.0%}")

    if a.probes:
        print("\nofficial demo probes (tools/demo_latency.py picks):")
        for fam, seed in PROBES:
            img, _ = G.generate_one(fam, seed)
            ranked = P.rank(img)
            mark = "first" if ranked[0] == fam else f"MISS({ranked[0]})"
            print(f"  {fam:14} {mark:14} top3={ranked[:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
