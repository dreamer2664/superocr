#!/usr/bin/env python3
"""Character-level analysis of a bench report (S10, 12 Oct).

Bench counts ITEMS. The bar is 98/100 exact strings, so what matters is the
per-character accuracy of the read, not the item accuracy. This tool turns a
bench JSON into the numbers that explain the gap:

  * per-character accuracy implied by the edit distances on failed items,
  * how many items fail ONLY on case (would pass with perfect case calls),
  * how many fail ONLY on spacing (all glyphs right, word grouping wrong),
  * the per-character accuracy the bar actually demands at the measured mean
    label length: bar^(1/meanlen) - i.e. "how good does a glyph have to be".

Usage:
  python3 tools/suite_char_analysis.py --report <bench.json> [--report ...]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[len(b)]


def bar_per_char(bar_pct: float, mean_len: float) -> float:
    """Per-character accuracy needed for `bar_pct` of whole strings to be exact."""
    return (bar_pct / 100.0) ** (1.0 / mean_len) if mean_len else float("nan")


def analyse_suite(res: list[dict], bar: float) -> dict:
    total = len(res)
    correct = sum(1 for i in res if i["match"])
    lens = [len(i["label"]) for i in res]
    mean_len = sum(lens) / total if total else 0.0
    chars = sum(lens)
    dist = Counter()
    case_only = space_only = 0
    edits = 0
    for i in res:
        if i["match"]:
            continue
        exp, got = i["label"], i["got"] or ""
        d = levenshtein(exp, got)
        dist[d] += 1
        edits += d
        if exp.lower() == got.lower():
            case_only += 1
        elif exp.replace(" ", "") == got.replace(" ", ""):
            space_only += 1
    return {
        "items": total,
        "exact": correct,
        "bar": bar,
        "mean_label_len": round(mean_len, 1),
        "total_chars": chars,
        "edit_distance_sum": edits,
        "per_char_acc_measured": round(1 - edits / chars, 4) if chars else None,
        "per_char_acc_needed_for_bar": round(bar_per_char(bar, mean_len), 5),
        "fails": total - correct,
        "fails_case_only": case_only,
        "fails_space_only": space_only,
        "fails_within_1_edit": dist[1],
        "fails_within_2_edits": dist[1] + dist[2],
        "edit_distance_hist": dict(sorted(dist.items())),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--report", action="append", required=True,
                   help="bench report JSON (repeat for several)")
    p.add_argument("--json", default=None, help="write the full analysis here")
    args = p.parse_args()

    out = {}
    for path in args.report:
        r = json.load(open(path))
        bits = {}
        for suite, s in r["suites"].items():
            res = s["results"]
            bar = s.get("bar", 98 if suite == "easy" else 95)
            bits[suite] = analyse_suite(res, bar)
        out[path] = {"reader": r.get("reader"), "run_id": r.get("run_id"),
                     "suites": bits}
        print(f"== {path}")
        print(f"   reader: {r.get('reader')}")
        for suite, a in bits.items():
            print(f"   {suite}: exact {a['exact']}/{a['items']} "
                  f"(bar {a['bar']}) | mean label {a['mean_label_len']} chars")
            print(f"     per-char accuracy measured {a['per_char_acc_measured']:.4f} "
                  f"| needed for the bar {a['per_char_acc_needed_for_bar']:.5f} "
                  f"({100 * (1 - a['per_char_acc_needed_for_bar']):.2f}% error budget)")
            print(f"     failures: {a['fails']} | case-only {a['fails_case_only']} "
                  f"| spacing-only {a['fails_space_only']} "
                  f"| within 1 edit {a['fails_within_1_edit']} "
                  f"| within 2 edits {a['fails_within_2_edits']}")
    if args.json:
        json.dump(out, open(args.json, "w"), indent=2, sort_keys=True)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
