#!/usr/bin/env python3
"""S13 regression lock (t-20261012-44c0): the floor reads official suite item
dod-0001 EXACTLY. The S7c rev-1 sigma-25 wiring regressed this item to
'HazH...'; rev-2 un-wired it. Suite image dark-on-dark-0001 == generator
seed 1, index 1 (byte-verified), so the test regenerates it in-process —
no data/ dependency (datasets are generated, not committed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402
import baseline  # noqa: E402


def test_floor_reads_dod_0001_exactly():
    img, label = G.generate_one("dark-on-dark", seed=1, index=1)
    assert label == "walrus BrooK cOmeT Penguin Hazel", \
        f"generator drifted: {label!r}"
    text, _ = baseline.read_text(img)  # no family: the floor path
    assert text.strip() == label, (
        f"dod-0001 regressed: floor read {text.strip()!r}, label {label!r}")


def main() -> int:
    try:
        test_floor_reads_dod_0001_exactly()
        print("PASS  test_floor_reads_dod_0001_exactly")
        print("OK: dod-0001 floor lock holds")
        return 0
    except AssertionError as e:
        print(f"FAIL  test_floor_reads_dod_0001_exactly: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
