#!/usr/bin/env python3
"""s50_confusion_probe.py — S50 (t-20261013-ef0a): pattern-based error
correction, measured — NOT wired.

Closed-lane context: S22 (lex re-casing) was rejected; S24/S25 closed the
case lane with converging negatives; the shipping route already runs
reader_lex = floor + lex-projection (vocab-distance substitution repair
R1-R4 + S25 count repairs). So the honest S50 question is: after all
that, which misses are still ONE confusion-pair substitution away from
truth, what context distinguishes them, and would context-aware rules
break currently-correct reads?

  1. read easy+hard suites in-process (baseline.read_text + fix_line —
     verified identical to the reader_lex CLI)
  2. for every miss: char-level alignment (Levenshtein backtrack),
     substitution ops classified into confusion pairs vs other damage
  3. fixable-if-one-swap: corrected == truth under a single confusion
     substitution (and two-swap counted separately)
  4. context rules simulated on the SAME reads:
       R-digit : token contains >=1 digit and <=4 chars -> digit-translate
                 the classic letter confusers (OoIlZSB -> 0011258)
       R-case  : token case-insensitively in vocab, first letter's case
                 flipped to match Titlecase label pattern
     each rule scored: fixes on misses vs BREAKS on correct reads
  5. verdict: net gain must be positive on BOTH suites with zero easy
     breaks to even propose wiring (bar discipline: beat 73/23 3x)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import baseline as B  # noqa: E402
from lex_projection import fix_line  # noqa: E402
import generator as G  # noqa: E402

CONFUSION = set("Oo0lI1Ss5B8Z2G6b6g9qQpP")
DIGIT_FIX = str.maketrans("OoIlZSB", "0011258")


def read_all(split: str):
    rows = [json.loads(l) for l in open(f"data/{split}/manifest.jsonl")]
    out = []
    for r in rows:
        img = Image.open(Path("data") / split / r["image"])
        raw, _conf = B.read_text(img)
        text = fix_line(raw)
        out.append((r["label"], text, r.get("family", "?")))
    return out


def align_ops(a: str, b: str):
    """Levenshtein backtrack: list of (i, got_char, truth_char) subs."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            if a[i - 1] != b[j - 1]:
                ops.append((i - 1, a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append((i - 1, a[i - 1], ""))
            i -= 1
        else:
            ops.append((j - 1, "", b[j - 1]))
            j -= 1
    return dp[n][m], ops


def one_swap_fixable(got: str, truth: str):
    """Is got exactly one confusion-pair substitution away from truth?"""
    if len(got) != len(truth):
        return False, None
    diffs = [(i, g, t) for i, (g, t) in enumerate(zip(got, truth)) if g != t]
    if len(diffs) != 1:
        return (len(diffs) <= 2 and len(diffs) > 0 and
                all(g in CONFUSION and t in CONFUSION for _, g, t in diffs),
                diffs if diffs else None)
    i, g, t = diffs[0]
    return (g in CONFUSION and t in CONFUSION), diffs


def rule_digit(text: str) -> str:
    toks = text.split(" ")
    out = []
    for tok in toks:
        if (tok and any(c.isdigit() for c in tok) and len(tok) <= 4
                and not tok.isdigit()):
            cand = tok.translate(DIGIT_FIX)
            if cand.isdigit():
                tok = cand
        out.append(tok)
    return " ".join(out)


def rule_case(text: str) -> str:
    toks = text.split(" ")
    out = []
    for tok in toks:
        if tok and tok[0].islower() and tok.lower() in G._WORDS and len(tok) > 1:
            tok = tok[0].upper() + tok[1:]
        out.append(tok)
    return " ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/s50-confusion/probe.json")
    args = ap.parse_args()
    report = {"rules": {}, "splits": {}}

    for split in ("hard", "easy"):
        rows = read_all(split)
        correct = [r for r in rows if r[1] == r[0]]
        misses = [r for r in rows if r[1] != r[0]]
        print(f"\n=== {split}: {len(correct)} correct, {len(misses)} misses ===",
              flush=True)

        # miss anatomy
        sub_counter = Counter()
        one_swap, two_swap, other = [], [], []
        for label, text, fam in misses:
            dist, ops = align_ops(text, label)
            subs = [(i, g, t) for i, g, t in ops if g and t]
            for _, g, t in subs:
                sub_counter[f"{g}->{t}"] += 1
            ok, diffs = one_swap_fixable(text, label)
            if ok and diffs and len(diffs) == 1:
                one_swap.append((text, label, diffs, fam))
            elif ok and diffs:
                two_swap.append((text, label, diffs, fam))
            else:
                other.append((text, label, dist, fam))
        print(f"  one confusion-swap from truth: {len(one_swap)}")
        for t, l, d, f in one_swap:
            print(f"    [{f}] {t!r} -> {l!r} {d}")
        print(f"  two confusion-swaps: {len(two_swap)}")
        for t, l, d, f in two_swap:
            print(f"    [{f}] {t!r} -> {l!r} {d}")
        print(f"  other damage (seg/length/case-mixed): {len(other)}")
        print(f"  top substitutions: {sub_counter.most_common(12)}")

        # rule simulation: fixes on misses, breaks on corrects
        for rname, fn in (("R-digit", rule_digit), ("R-case", rule_case)):
            fixes = sum(1 for label, text, _ in misses if fn(text) == label)
            breaks = sum(1 for label, text, _ in correct if fn(text) != label)
            print(f"  {rname}: fixes {fixes}, breaks {breaks}")
            report["rules"].setdefault(rname, {})[split] = {
                "fixes": fixes, "breaks": breaks}

        report["splits"][split] = {
            "correct": len(correct), "misses": len(misses),
            "one_swap": [(t, l, d, f) for t, l, d, f in one_swap],
            "two_swap": [(t, l, d, f) for t, l, d, f in two_swap],
            "other_n": len(other),
            "substitutions": dict(sub_counter.most_common()),
        }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(args.out, "w"), indent=1)
    print(f"\nreport {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
