#!/usr/bin/env python3
"""S10b: the glyph-policy mirror must be the floor chain, and the policies
must do exactly what they say.

The S10b wiring changes one decision inside baseline.read_text: which
character a glyph piece gets. These tests pin that boundary:

  * the mirror under policy='floor' must reproduce baseline.read_text
    byte-for-byte on a real rendered image (the mirror is the thing the
    sweep and the probe measure through - if it drifts, every S10b number
    is fiction),
  * the case rule (baseline's SAME_SHAPE height rule) applies to whichever
    character survives the policy,
  * the gate accepts the CNN answer only when the floor score is below the
    gate AND the CNN probability is at least min-prob,
  * policy='cnn' prefers the CNN character on every recorded piece.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "readers"))

from s10b_gate import (apply_case, read_text_with, reconstruct,  # noqa: E402
                       verify_mirror)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


@pytest.fixture(scope="module")
def sample_img(tmp_path_factory):
    """A real rendered sample: the chain must actually find glyphs in it."""
    p = tmp_path_factory.mktemp("s10b") / "sample.png"
    img = Image.new("L", (520, 90), 255)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 42)
    d.text((12, 18), "Falcon Birch 91", font=f, fill=0)
    img.save(p)
    return Image.open(p)


def test_mirror_reproduces_the_chain(sample_img):
    chain, mirror = verify_mirror(sample_img)
    assert chain == mirror, f"mirror drifted: chain {chain!r} vs mirror {mirror!r}"
    assert chain != "", "sample must read as something - a blank read is vacuous"


def test_case_rule_uses_height_ratio():
    # tall piece -> upper, short piece -> lower (baseline's SAME_SHAPE rule)
    assert apply_case("O", 20, 20) == "O"
    assert apply_case("O", 10, 20) == "o"
    # characters outside SAME_SHAPE pass through untouched
    assert apply_case("r", 10, 20) == "r"


def _piece(ch, score, cnn_ch, cnn_p, h=20, cap=20):
    return {"ch": ch, "score": score, "cnn_ch": cnn_ch, "cnn_p": cnn_p,
            "h": h, "cap": cap}


def test_floor_policy_ignores_the_cnn():
    words = [[_piece("a", 0.2, "b", 1.0)]]
    assert reconstruct(words, policy="floor") == "a"
    assert reconstruct(words, policy="gate", gate=0.9, min_prob=0.5) == "b"
    assert reconstruct(words, policy="cnn") == "b"


def test_gate_needs_both_conditions():
    confident_floor = [[_piece("a", 0.99, "b", 1.0)]]   # floor above gate
    unsure_cnn = [[_piece("a", 0.2, "b", 0.3)]]         # CNN below min-prob
    assert reconstruct(confident_floor, policy="gate", gate=0.9, min_prob=0.5) == "a"
    assert reconstruct(unsure_cnn, policy="gate", gate=0.9, min_prob=0.5) == "a"
    assert reconstruct(unsure_cnn, policy="gate", gate=0.9, min_prob=0.1) == "b"


def test_cnn_policy_keeps_case_rule_and_layout():
    # word boundaries and the case rule survive the policy change; note the
    # case rule acts on the character that survived (the CNN's 'o' here)
    words = [[_piece("O", 1.0, "o", 1.0, h=20, cap=20),
              _piece("r", 1.0, "r", 1.0, h=10, cap=20)],
             [_piece("x", 1.0, "x", 1.0, h=10, cap=20)]]
    assert reconstruct(words, policy="cnn") == "Or x"
    # a full-height x-height letter is uppercased, same as the floor chain
    tall = [[_piece("x", 1.0, "x", 1.0, h=20, cap=20)]]
    assert reconstruct(tall, policy="cnn") == "X"
