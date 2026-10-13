#!/usr/bin/env python3
"""Regression pin for S25 count arbitration (t-20261013-0956, marcus's flag).

The placement is load-bearing: _s25_count_repairs must run POST-projection
in fix_line. A pre-projection wiring measured hard 22 instead of 23 — the
orphan 'L' in stitch-0005's raw output can only be dropped after fix_token
has projected 'alon' -> 'talon'. These tests pin the composition through
the REAL fix_line entry point (raw baseline-style text in), so a placement
change fails loudly.
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


@check("digit-join: adjacent digit-only tokens join when <=3 digits")
def _():
    assert fix_line("north TARN 2 3") == "north TARN 23"
    assert fix_line("COPPER 0 08 linen") == "COPPER 008 linen"


@check("alpha-orphan-drop BEFORE a clean token (mirror of R5's after-rule)")
def _():
    # raw baseline output form: the orphan precedes the fuzzy projection
    assert fix_line("L alon sha le 007") == "talon shale 007"
    assert fix_line("L talon shale 007") == "talon shale 007"


@check("digits are legal single tokens: never dropped")
def _():
    assert fix_line("pebble 2 CANYON") == "pebble 2 CANYON"
    assert fix_line("Violet 3 stalactite") == "Violet 3 stalactite"


@check("grammar invariant: no canonical label has adjacent digit tokens")
def _():
    import json
    for suite in ("easy", "hard"):
        man = ROOT / "data" / suite / "manifest.jsonl"
        if not man.exists():
            continue
        for line in man.read_text().splitlines():
            toks = json.loads(line)["label"].split()
            for a, b in zip(toks, toks[1:]):
                assert not (a.isdigit() and b.isdigit()), (suite, line)


@check("idempotence: fix_line(fix_line(x)) == fix_line(x)")
def _():
    for x in ("north TARN 2 3", "L alon sha le 007", "pebble 2 CANYON",
              "Comet MEriDIAn", "gLAcier bRo0k 002 Indigo"):
        once = fix_line(x)
        assert fix_line(once) == once, x


def main() -> int:
    ok = True
    for name, fn in CHECKS:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            ok = False
            print(f"FAIL  {name}  {e}")
    print(("ALL PASS" if ok else "FAILURES") + f" ({len(CHECKS)} checks)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
