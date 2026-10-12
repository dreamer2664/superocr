#!/usr/bin/env python3
"""S22 (t-20261012-dc2e): classify what is LEFT after the floor+lex route.

Receipt-based and read-only. Two input shapes, both accepted:

  * a floor-rows JSON (list of {id, suite, got, label})        -> add --lex to
    run the MERGED lex projection (tools/lex_projection.fix_line) over each
    raw read, i.e. the exact shipping wrapper route (reader_lex.py);
  * a bench receipt JSON (dict, suites.<s>.results)            -> classify as
    reported (use for receipts that are already post-lex).

No new claims beyond the input files + the reader itself — this is the
targeting map for the next easy/hard wave.

Usage:
    python3 tools/s22_residue.py --lex rows.json
    python3 tools/s22_residue.py receipt.json

Class rules (transparent, deliberately coarse):
    exact / case-only / fewer-chars / more-chars / subs(n)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lex_projection import fix_line  # noqa: E402


def classify(got: str, label: str) -> str:
    if got == label:
        return "exact"
    if got.lower() == label.lower():
        return "case-only"
    if len(got) < len(label):
        return "fewer-chars"
    if len(got) > len(label):
        return "more-chars"
    return f"subs({sum(1 for a, b in zip(got, label) if a != b)})"


def load_rows(path: str, lex: bool):
    d = json.load(open(path))
    items = []
    if isinstance(d, list):                       # floor rows
        for r in d:
            got = fix_line(r["got"]) if lex else r["got"]
            items.append((r["suite"], r["id"], got, r["label"]))
    else:                                          # bench receipt
        for s, v in d.get("suites", {}).items():
            for it in v.get("results", v.get("items", [])):
                got = it["got"] if isinstance(it, dict) else it[0]
                lab = it["label"] if isinstance(it, dict) else None
                items.append((s, it["id"] if isinstance(it, dict) else None, got, lab))
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    ap.add_argument("--lex", action="store_true",
                    help="apply the merged lex projection to each raw read")
    ap.add_argument("--labels-from", default=None,
                    help="bench receipt to take labels from when input has none")
    args = ap.parse_args()

    items = load_rows(args.path, args.lex)
    if args.labels_from:
        lab = {}
        d = json.load(open(args.labels_from))
        for s, v in d["suites"].items():
            for it in v["results"]:
                lab[it["id"]] = it["label"]
        items = [(s, i, g, lab.get(i, l)) for s, i, g, l in items]

    print(f"== {args.path}" + (" (post-lex)" if args.lex else ""))
    for suite in sorted({s for s, *_ in items}):
        sub = [x for x in items if x[0] == suite]
        c = Counter()
        misses = []
        for s, i, got, label in sub:
            k = classify(got, label) if label is not None else "?"
            c[k] += 1
            if k != "exact":
                misses.append((i, k, got, label))
        n = len(sub)
        print(f"   {suite}: {c['exact']}/{n} exact | "
              f"{dict(sorted(c.items(), key=lambda x: -x[1]))}")
        for i, k, got, label in misses:
            print(f"      {i:18s} [{k:11s}] {got!r} != {label!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
