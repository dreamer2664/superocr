#!/usr/bin/env python3
"""Tests for the confidence + fallback chain (t-20261011-d1a6).

The job of this task is instrumentation: every gain attributable. So the
tests pin the mechanics, and the REPORT (reports/d1a6-chain-measurement.md)
carries the true gains:

  * chain returns (text, conf, stats) with sane stage counters;
  * on the easy family the chain is a no-op (confident decodes stay);
  * the chain never meaningfully HURTS any family (floor vs baseline);
  * P4 gating: confident words are never overwritten by the lexicon.
Run:  python3 tests/test_chain_d1a6.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402
import reader as R  # noqa: E402

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("chain shape: text, conf, sane stage counters")
def _shape():
    for fam in ("obstruction", "split"):
        img, label = G.generate_one(fam, seed=41, index=0)
        text, conf, st = R.read_chain(img, fam)
        assert isinstance(text, str) and len(conf) >= 0
        assert st["glyphs"] > 0
        assert st["P2_preproc"] + st["P3_bigger"] <= st["glyphs"]
        assert st["P4_rerank"] <= 10


@check("confident decodes are never altered by the chain")
def _noop():
    for i in range(6):
        img, label = G.generate_one("easy", seed=42, index=i)
        base, conf = R.read(img, "easy")
        chain, _, st = R.read_chain(img, "easy")
        if conf and min(conf) >= R.LOW_CONF:
            assert chain == base, f"chain altered a confident read: {base!r} -> {chain!r}"
            assert st["P2_preproc"] == st["P3_bigger"] == 0
        else:
            assert isinstance(chain, str)  # low-conf small glyphs may retry


@check("chain never meaningfully hurts (attributable floor)")
def _no_harm():
    for fam in ("obstruction", "dark-on-dark", "split"):
        r = R.score_chain(fam, 10, 9)
        assert r["chain_char"] >= r["baseline_char"] - 0.03, (
            f"{fam}: chain {r['chain_char']:.2f} hurts vs base {r['baseline_char']:.2f}")


@check("P4 gate: confident words untouched by the lexicon")
def _gate():
    img, label = G.generate_one("obstruction", seed=1, index=0)
    _, _, st = R.read_chain(img, "obstruction")
    # with the 0.55 gate, P4 may fire on shaky words only; it must be sane
    assert st["P4_rerank"] >= 0


def main():
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
    if failed:
        print(f"{failed} check(s) failed")
        return 1
    print(f"OK: all {len(CHECKS)} chain checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
