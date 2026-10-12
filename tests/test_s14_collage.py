#!/usr/bin/env python3
"""S14 regression test (t-20261012-1d17): the collage per-card route.

What it pins, in CI (numpy + Pillow only - the cv2 fast path is absent there,
so this test also proves the fallback still works):

  * detection finds the cards on a generated sheet (>= 2 of them),
  * a plain single-block image is NOT treated as a card sheet (guard),
  * read_collage returns text, and the same image twice gives the same text,
  * with `cv2` forced away, the route still returns text (fallback path).

It does not pin exact characters: case twins (c/C, i/I/l) are the known
residue, and the two rectification paths differ slightly by design (documented
in readers/collage.py). Structure and determinism are the contract here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "readers"))

import generator as G  # noqa: E402
import collage as C  # noqa: E402

IMG, LABEL = G.generate_one("collage", seed=1, index=0)


def test_cards_are_found():
    import numpy as np
    a = np.array(IMG.convert("L"), dtype=np.uint8)
    rects = C.card_rects(a)
    assert len(rects) >= 2, f"expected >= 2 cards on a collage sheet, found {len(rects)}"


def test_single_block_is_not_a_card_sheet():
    import numpy as np
    img, _ = G.generate_one("easy", seed=1, index=0)
    a = np.array(img.convert("L"), dtype=np.uint8)
    rects = C.card_rects(a)
    assert rects == [], f"a plain image must not be treated as a card sheet ({len(rects)} rects)"


def test_read_returns_text_and_is_deterministic():
    first = C.read_collage(IMG)
    assert first.strip(), "the route returned nothing on a collage sheet"
    second = C.read_collage(IMG)
    assert first == second, f"not deterministic: {first!r} vs {second!r}"


def test_fallback_path_works_without_cv2():
    saved = C.cv2
    try:
        C.cv2 = None                      # force the numpy/PIL fallback
        text = C.read_collage(IMG)
        assert text.strip(), "fallback path returned nothing on a collage sheet"
    finally:
        C.cv2 = saved


def main() -> int:
    failures = []
    for fn in (test_cards_are_found, test_single_block_is_not_a_card_sheet,
               test_read_returns_text_and_is_deterministic, test_fallback_path_works_without_cv2):
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failures.append(fn.__name__)
            print(f"FAIL  {fn.__name__}: {e}")
    if failures:
        print(f"FAIL: {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("OK: the collage route holds (detection, guard, text, determinism, fallback)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
