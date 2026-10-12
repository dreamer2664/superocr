#!/usr/bin/env python3
"""Regression bars for S7 part 1 (t-20261012-e199): the band/vignette walls.

cross-shadow : shadow bands kill every global threshold; the local-contrast
               mask (local_diff_mask) is band-immune and is now the primary
               variant, read through read_chain.
dark-on-dark : a bigger background sigma + low threshold keeps the
               vignette-dimmed strokes the old residual path dropped.

Bars sit below the measured seed-7 numbers (0.528 / 0.474 on this 5-image
subset) and well above the pre-fix readings (0.175 / 0.351), so a silent
reversion to the wall fails loudly. Run: python3 -m pytest tests/test_walls_e199.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import reader as R  # noqa: E402


def test_cross_shadow_local_diff_beats_the_bands():
    r = R.score("cross-shadow", 5, seed=7)
    assert r["char_acc"] >= 0.40, (
        f"cross-shadow wall is back: char {r['char_acc']:.3f} < 0.40 "
        "(pre-fix floor was 0.175 on this subset)")


def test_dark_on_dark_vignette_strokes_survive():
    r = R.score("dark-on-dark", 5, seed=7)
    assert r["char_acc"] >= 0.42, (
        f"dark-on-dark vignette stroke loss is back: char {r['char_acc']:.3f} "
        "< 0.42 (pre-fix floor was 0.351 on this subset)")


def test_darts_dark_core_severs_the_web():
    """Dart webs fuse glyphs into line-spanning mega-blobs (char 0.014 on the
    floor); the dark-core mask severs them. Bar sits below the measured
    seed-7 subset (0.717) and 15x above the pre-fix reading."""
    r = R.score("darts", 5, seed=7)
    assert r["char_acc"] >= 0.55, (
        f"darts fusion is back: char {r['char_acc']:.3f} < 0.55 "
        "(pre-fix floor was 0.014)")


def test_corrosion_floor_holds():
    """Corrosion is still a wall, but the wired floor (chain + close1) must
    not regress: measured 0.171 on seed-7 tens, bar under it."""
    r = R.score("corrosion", 5, seed=7)
    assert r["char_acc"] >= 0.13, (
        f"corrosion floor dropped: char {r['char_acc']:.3f} < 0.13")


def test_local_diff_mask_is_band_immune():
    """The LD mask must carry ink inside the shadow bands: on a cross-shadow
    image it covers a non-trivial fraction of the frame where plain Otsu
    collapses (bands read as ink or wipe rows entirely)."""
    import generator as G
    img, _ = G.generate_one("cross-shadow", seed=7, index=0)
    m = R.trim(R.local_diff_mask(img, 25, 60.0))
    assert m.any()
    assert m.mean() >= 0.02, f"LD mask suspiciously empty: {m.mean():.4f}"
