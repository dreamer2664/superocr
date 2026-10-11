#!/usr/bin/env python3
"""Tests for the glyph classifier and the end-to-end reader (t-20261011-f0d2).

The important test here is the gradient check: a hand-written numpy backward
pass fails silently — the model still trains (a wrong-but-consistent backward
can still descend) and only the final accuracy reveals it, hours later. This
file pins the maths against finite differences in float64, against a naive
loop convolution, and against a save/load round trip.

    python3 tests/test_glyphcnn.py
    python3 -m unittest discover -s tests -v

Stdlib + numpy + PIL only, offline, seeded, fast (~15 s; the smoke training
run is 1 epoch on a tiny dataset).
"""

import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "readers"))


def naive_conv(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Reference convolution with same-padding, written for clarity."""
    n, c, h, ww = x.shape
    o, _, kh, kw = w.shape
    xp = np.pad(x, ((0, 0), (0, 0), (kh // 2, kh // 2), (kw // 2, kw // 2)))
    out = np.zeros((n, o, h, ww))
    for ni in range(n):
        for oi in range(o):
            for y in range(h):
                for xx in range(ww):
                    acc = b[oi]
                    for ci in range(c):
                        for i in range(kh):
                            for j in range(kw):
                                acc += xp[ni, ci, y + i, xx + j] * w[oi, ci, i, j]
                    out[ni, oi, y, xx] = acc
    return out


def render_label(text: str, size: int = 34) -> Image.Image:
    font = None
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if os.path.exists(candidate):
            font = ImageFont.truetype(candidate, size)
            break
    if font is None:
        font = ImageFont.load_default(size=size)
    img = Image.new("RGB", (40 + 26 * len(text), int(size * 2.2)), (248, 248, 248))
    ImageDraw.Draw(img).text((16, int(size * 0.5)), text, fill=(24, 24, 24), font=font)
    return img


class GlyphCNNTest(unittest.TestCase):
    # ---- the maths -------------------------------------------------------

    def test_conv_forward_matches_naive_reference(self):
        from glyphcnn import conv_forward
        rng = np.random.default_rng(0)
        x = rng.standard_normal((2, 3, 6, 6))
        w = rng.standard_normal((4, 3, 3, 3))
        b = rng.standard_normal(4)
        fast = conv_forward(x, w, b)
        slow = naive_conv(x, w, b)
        self.assertTrue(np.allclose(fast, slow, atol=1e-9),
                        f"max diff {np.abs(fast - slow).max():.2e}")

    def test_gradient_check_all_parameters(self):
        """Finite differences vs the hand-written backward, in float64."""
        from glyphcnn import N_CLASSES, GlyphCNN
        rng = np.random.default_rng(1)
        net = GlyphCNN(seed=0)
        net.p = {k: v.astype(np.float64) for k, v in net.p.items()}
        x = rng.random((5, 1, 24, 24))
        y = rng.integers(0, N_CLASSES, 5)
        _, g = net.loss_and_grads(x, y)
        eps = 1e-6
        worst = 0.0
        for k in net.p:
            flat = net.p[k].ravel()
            for idx in rng.choice(len(flat), size=min(3, len(flat)), replace=False):
                orig = flat[idx]
                flat[idx] = orig + eps
                lp, _ = net.loss_and_grads(x, y)
                flat[idx] = orig - eps
                lm, _ = net.loss_and_grads(x, y)
                flat[idx] = orig
                numeric = (lp - lm) / (2 * eps)
                analytic = g[k].ravel()[idx]
                rel = abs(numeric - analytic) / max(1e-12, abs(numeric) + abs(analytic))
                worst = max(worst, rel)
        self.assertLess(worst, 1e-5, f"worst relative gradient error {worst:.2e}")

    def test_save_load_roundtrip_is_exact(self):
        from glyphcnn import N_CLASSES, GlyphCNN
        rng = np.random.default_rng(2)
        net = GlyphCNN(seed=3)
        x = rng.random((4, 1, 24, 24)).astype(np.float32)
        before = net.forward(x)[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.npz")
            net.save(path)
            again = GlyphCNN.load(path)
            after = again.forward(x)[0]
        self.assertTrue(np.array_equal(before, after))
        self.assertEqual(again.width, net.width)

    # ---- segmentation ----------------------------------------------------

    def test_segmentation_finds_the_glyphs_and_the_word_gap(self):
        from segmentation import analyse
        img = render_label("aB 3x")
        _, boxes = analyse(img)
        self.assertEqual(len(boxes), 4, f"expected 4 glyph boxes, got {len(boxes)}")
        spaces = [s for _, s in boxes]
        self.assertEqual(spaces, [False, False, True, False],
                         f"word gap not found in the right place: {spaces}")

    def test_ink_mask_is_not_the_whole_image(self):
        from segmentation import ink_mask
        mask = ink_mask(render_label("Hello"))
        frac = mask.mean()
        self.assertLess(frac, 0.2, f"ink fraction {frac:.3f} means polarity is inverted")
        self.assertGreater(frac, 0.001)

    def test_deskew_recovers_a_known_tilt(self):
        from segmentation import deskew, ink_mask
        img = render_label("aB 3x")
        tilted = img.rotate(5, resample=Image.BICUBIC, fillcolor=(248, 248, 248))
        _, angle = deskew(ink_mask(tilted))
        self.assertLess(abs(angle + 5.0), 1.2, f"deskew found {angle}, expected about -5")

    # ---- end to end ------------------------------------------------------

    def test_reader_smoke_trains_a_tiny_model_and_reads(self):
        """The whole chain: train 1 epoch on a few crops, then read an image."""
        with tempfile.TemporaryDirectory() as tmp:
            weights = os.path.join(tmp, "tiny.npz")
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "tools", "train_glyphs.py"),
                 "--per-class", "2", "--epochs", "1", "--generator-sheets", "0",
                 "--no-cache", "--out", weights,
                 "--data", os.path.join(tmp, "d.npz")],
                capture_output=True, text=True, timeout=600, cwd=ROOT)
            self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
            self.assertTrue(os.path.exists(weights))
            image = os.path.join(tmp, "word.png")
            render_label("AB").save(image)
            read = subprocess.run(
                [sys.executable, os.path.join(ROOT, "readers", "cnn_reader.py"),
                 "--image", image, "--weights", weights],
                capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(read.returncode, 0, read.stderr[-500:])
            text = read.stdout.rstrip("\n")
            self.assertEqual(len(text), 2,
                             f"two glyphs in, {len(text)} out: {text!r}")

    def test_committed_weights_and_recipe_agree(self):
        """If the model is committed, the recipe must describe it honestly."""
        import json
        weights = os.path.join(ROOT, "models", "glyphcnn.npz")
        recipe = os.path.join(ROOT, "recipes", "glyphcnn.json")
        if not os.path.exists(weights):
            self.skipTest("no committed weights yet")
        self.assertTrue(os.path.exists(recipe), "weights without a recipe are not reproducible")
        size = os.path.getsize(weights)
        self.assertLess(size, 10 * 1024 * 1024, "JOBS.md: commit weights only under 10 MB")
        with open(recipe, encoding="utf-8") as fh:
            info = json.load(fh)
        with np.load(weights) as data:
            self.assertIn("w1", data.files)
            self.assertEqual(data["w1"].shape[0], 8)
        self.assertIn("final_val_acc", info)
        self.assertLessEqual(info["final_val_acc"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
