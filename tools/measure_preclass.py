#!/usr/bin/env python3
"""measure_preclass.py — how good is the auto-mode shortlist, honestly.

The pre-classifier (preclass.shortlist) routes auto mode; this tool measures
that routing against the repo's own generator as ground truth, on seeds you
name (default 404) that were NOT used while tuning the thresholds.

Reported per family, over N samples each:
  in-shortlist : the true family is among those auto would run (it can win)
  routed-first : the true family's rule fired strongest (auto tries it first)

Both numbers matter and they are different: a family can be in the running
and still lose the confidence argmax to `easy` — that is a reader question,
not a routing one, and this tool never pretends otherwise.

Usage: python3 tools/measure_preclass.py [--seed 404] [--per-class 10] [--probes]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generator as G      # noqa: E402
import preclass as P       # noqa: E402

FAMILIES = ["easy"] + [f for f in G.FAMILIES if f != "easy"]
PROBES = (("easy", 11), ("snow", 12), ("obstruction", 13),
          ("split", 14), ("strippy", 15), ("dark-on-dark", 16))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=404)
    ap.add_argument("--per-class", type=int, default=10)
    ap.add_argument("--probes", action="store_true",
                    help="also show the six official demo probes")
    a = ap.parse_args(argv)

    print(f"held-out seed {a.seed}, {a.per_class} per family "
          f"(never used for tuning):")
    tot = hit = first = 0
    for fam in FAMILIES:
        h = f1 = 0
        for i in range(a.per_class):
            img, _ = G.generate_one(fam, a.seed, index=i)
            short, _ = P.shortlist(img)
            h += int(fam in short)
            f1 += int(short[0] == fam)
        print(f"  {fam:14} in-shortlist {h:>2}/{a.per_class}   "
              f"routed-first {f1:>2}/{a.per_class}")
        tot += a.per_class
        hit += h
        first += f1
    print(f"  TOTAL          in-shortlist {hit}/{tot} = {hit/tot:.0%}   "
          f"routed-first {first}/{tot} = {first/tot:.0%}")

    if a.probes:
        print("\nofficial demo probes (tools/demo_latency.py picks):")
        for fam, seed in PROBES:
            img, _ = G.generate_one(fam, seed)
            short, info = P.shortlist(img)
            mark = "in " if fam in short else "MISS"
            print(f"  {fam:14} {mark} shortlist={short} "
                  f"strong={info['strong']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
