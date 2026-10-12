#!/usr/bin/env python3
"""S10: the generator-harvest agreement gate must actually gate.

The gate exists as data hygiene: a sheet whose boxes the classic matcher
cannot mostly read back is a sheet whose pieces are probably misaligned, and
misaligned pieces mean a fragment labelled with a full glyph (see the S10
report). The rule is drop-the-sheet, never relabel.

These tests pin the mechanism, not the score: with the matcher forced to
disagree, no sheet may pass; with the gate off, the same sheets must still
produce crops (so the "0 crops" assertion cannot pass vacuously).
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # run_all.py executes this file as a
sys.path.insert(0, str(ROOT / "tools"))    # script: the repo root is not on
sys.path.insert(0, str(ROOT / "readers"))  # the path unless we put it there

import reader as R  # noqa: E402
import train_glyphs as T  # noqa: E402


@pytest.fixture(scope="module")
def gen():
    return T.load_generator()


def test_gate_off_harvests_something(gen):
    """Control run: with min_agree=0.0 the box-count filter alone admits crops."""
    x, y = T.crops_from_generator(gen, 40, 12, 24, verbose=False, min_agree=0.0)
    assert len(x) > 0, "control harvest produced nothing - test would be vacuous"
    assert len(x) == len(y)


def test_gate_drops_sheets_when_matcher_disagrees(gen, monkeypatch):
    """With a matcher that never agrees, the gate must keep zero crops."""
    monkeypatch.setattr(R, "match_glyph", lambda g: ("#", 1.0))
    x, y = T.crops_from_generator(gen, 40, 12, 24, verbose=False, min_agree=0.85)
    assert len(x) == 0, "gate admitted sheets despite total matcher disagreement"
    assert len(y) == 0


if __name__ == "__main__":            # run_all.py executes this file as a
    raise SystemExit(pytest.main([__file__, "-q"]))   # script: run for real
