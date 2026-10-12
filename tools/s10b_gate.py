#!/usr/bin/env python3
"""s10b_gate.py — S10b: the floor chain with a pluggable glyph policy.

Shared machinery for the S10b wiring: a faithful mirror of
`baseline.read_text`'s orchestration whose per-piece character decision is a
policy, plus the recorder/reconstruction used by `s10b_sweep.py` to evaluate
any threshold pair offline from one pass.

Policies (S10b, 12 Oct):

  floor   the chain's own template answer (identical to baseline.read_text)
  gate    the chain's answer, but when its template score is below `gate` and
          the CNN's probability is at least `min_prob`, the CNN's character
          wins (the confidence-gated fallback the brief asked for)
  cnn     the CNN reads every piece; the chain keeps the layout (its
          segmentation, splitting and word grouping)

Whoever wires S10b into baseline.py should keep the policy boundary here: the
chain's structure stays untouched, only the character decision changes.

The mirror self-checks against the real chain: `verify_mirror(img)` returns
the chain's own read and the mirror's floor read; they must be equal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))

import baseline as B  # noqa: E402
from segmentation import normalise_glyph  # noqa: E402


class Net:
    """Lazy glyphcnn-v2 loader: pieces are classified in one batch per image."""

    def __init__(self, weights: str | None = None) -> None:
        from glyphcnn import CHARS, GlyphCNN
        w = weights or str(ROOT / "models" / "glyphcnn-v2.npz")
        self.net = GlyphCNN.load(w)
        self.chars = CHARS

    def opinions(self, pieces: list[np.ndarray]) -> list[tuple[str, float]]:
        if not pieces:
            return []
        crops = [normalise_glyph(p.astype(bool), (0, 0, p.shape[1] - 1, p.shape[0] - 1))
                 for p in pieces]
        batch = np.stack(crops)[:, None, :, :].astype(self.net.p["w1"].dtype)
        probs = self.net.forward(batch)[0]
        out = []
        for pr in probs:
            idx = int(np.argmax(pr))
            out.append((self.chars[idx], float(pr[idx])))
        return out


def chain_pieces(img: Image.Image):
    """The floor chain's words -> pieces, exactly as baseline.read_text builds
    them (same helpers, same filters, same order)."""
    R = B.R
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.otsu(a)
    # polarity guard (t-20261011-be57): see baseline.read_text
    if mask.mean() > 0.5:
        mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    words = []
    for word in R.segment(mask):
        pieces = []
        for x0, x1 in word:
            for g in B._merge_forced(B._split_marked(R.trim(mask[:, x0:x1]))):
                if g.shape[0] >= 6 and g.sum() >= 10:
                    pieces.append(g)
        if pieces:
            words.append(pieces)
    return words


def apply_case(ch: str, h: int, cap: int) -> str:
    """baseline's SAME_SHAPE rule, applied to whatever character survived."""
    if ch in B.SAME_SHAPE:
        return ch.lower() if h < 0.85 * cap else ch.upper()
    return ch


def read_text_with(img: Image.Image, policy: str = "floor", gate: float = 0.9,
                   min_prob: float = 0.5, net: Net | None = None) -> str:
    """One read under a policy. 'floor' is byte-identical to baseline.read_text."""
    words = chain_pieces(img)
    if policy == "cnn" and net is None:
        net = Net()
    out = []
    for pieces in words:
        cap = max(g.shape[0] for g in pieces)
        ops = net.opinions(pieces) if (net is not None and policy in ("gate", "cnn")) else None
        chars = []
        for i, g in enumerate(pieces):
            ch, s = B.match_native(g)
            if ops is not None:
                cch, cprob = ops[i]
                if policy == "cnn" or (policy == "gate" and s < gate and cprob >= min_prob):
                    ch = cch
            chars.append(apply_case(ch, int(g.shape[0]), int(cap)))
        if chars:
            out.append("".join(chars))
    return " ".join(out)


def reconstruct(words: list[list[dict]], policy: str = "gate", gate: float = 0.9,
                min_prob: float = 0.5, case_rule: bool = True) -> str:
    """Build a read from recorded pieces under any policy (offline).

    Each piece dict carries: ch, score (floor), cnn_ch, cnn_p when the CNN
    opinion was recorded, h and cap for the case rule.
    """
    out = []
    for word in words:
        chars = []
        for p in word:
            ch = p["ch"]
            if policy == "cnn" and "cnn_ch" in p:
                ch = p["cnn_ch"]
            elif (policy == "gate" and "cnn_ch" in p and p["score"] < gate
                  and p.get("cnn_p", 0.0) >= min_prob):
                ch = p["cnn_ch"]
            if case_rule:
                ch = apply_case(ch, p["h"], p["cap"])
            chars.append(ch)
        if chars:
            out.append("".join(chars))
    return " ".join(out)


def verify_mirror(img: Image.Image) -> tuple[str, str]:
    """(chain read, mirror floor read) - must be equal, or the mirror drifted."""
    return B.read_text(img)[0], read_text_with(img, policy="floor")
