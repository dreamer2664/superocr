#!/usr/bin/env python3
"""Regression pin for the S55 lex R3 band widening (t-20261013-90e8).

The band in tools/lex_projection.py is max(1, round(len/3)) + 1 since S55.
That one line measured seed-1 73/23 -> 75/25 with zero broken rows, and
the gain depends on the uniqueness margin staying exactly as strict as
before: distance ties must still abstain. These checks pin BOTH sides
through the real fix_line entry point, so narrowing, further widening, or
margin loosening each fail loudly.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lex_projection import fix_line  # noqa: E402

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("S55 recovery: distance-3 unique projection at len 6 (stitch-0001)")
def _():
    assert fix_line("njMDRA harbor") == "TUNDRA harbor"


@check("S55 gain: distance-2 projection at len 4 (easy-0002 token)")
def _():
    assert fix_line("HORD") == "FJORD"


@check("tie abstention intact: 'rert' ties crest/reef at distance 2")
def _():
    assert fix_line("HEATHER rert") == "HEATHER rert"


@check("tie abstention intact: 'cafmon' 3-way tie canyon/carbon/salmon")
def _():
    line = "brass tide canyon cafmon nebULA"
    assert fix_line(line) == line


@check("R1 unchanged: clean vocabulary tokens are never re-cased")
def _():
    assert fix_line("Meteor CoPPER nebULA") == "Meteor CoPPER nebULA"


@check("far garble unchanged: 'zztlz' (nearest distance 4) left alone")
def _():
    assert fix_line("zztlz") == "zztlz"


def main():
    bad = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  ok  {name}")
        except AssertionError as e:
            bad += 1
            print(f"FAIL  {name}: {e}")
    print(f"{len(CHECKS) - bad}/{len(CHECKS)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
