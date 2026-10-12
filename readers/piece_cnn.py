#!/usr/bin/env python3
"""piece_cnn.py — glyphcnn-v2 applied to isolated glyph pieces (S10b).

The floor chain (baseline.py) isolates glyph pieces with classic primitives
and reads each one against rendered templates. S10b measured that its template
confidence is saturated (score 1.0 on ~98% of easy pieces, right or wrong), so
a confidence-gated fallback buys nothing: the promotable policy is to let the
CNN read the pieces while the floor keeps the layout.

This module is the CNN half of that policy, and the single place where the
piece -> 24x24 crop conversion lives, so training (tools/train_glyphs.py), the
standalone reader (readers/cnn_reader.py), the S10b probe and the wiring in
baseline.py all feed the network the same distribution: normalise_glyph() from
readers/segmentation.py, ink-bright, aspect preserved, centred.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "readers"))

from glyphcnn import CHARS, GlyphCNN  # noqa: E402
from segmentation import normalise_glyph  # noqa: E402

DEFAULT_WEIGHTS = str(ROOT / "models" / "glyphcnn-v2.npz")


class PieceCNN:
    """Batched second opinion for glyph pieces (one forward per batch)."""

    def __init__(self, weights: str | None = None) -> None:
        self.net = GlyphCNN.load(weights or DEFAULT_WEIGHTS)
        self.chars = CHARS

    def opinions(self, pieces: list[np.ndarray]) -> list[tuple[str, float]]:
        """(character, probability) for each piece, in order."""
        if not pieces:
            return []
        crops = [normalise_glyph(p.astype(bool),
                                 (0, 0, p.shape[1] - 1, p.shape[0] - 1))
                 for p in pieces]
        batch = np.stack(crops)[:, None, :, :].astype(self.net.p["w1"].dtype)
        probs = self.net.forward(batch)[0]
        out = []
        for pr in probs:
            idx = int(np.argmax(pr))
            out.append((self.chars[idx], float(pr[idx])))
        return out
