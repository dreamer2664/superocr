#!/usr/bin/env python3
"""Auto-mode latency and routing bars (t-20261012-5c63, S9).

JOBS.md's product bar: an auto-mode probe answers in under 10 s. Before this
change auto ran all thirteen family chains and took the loudest confidence;
measured on these same pinned probe images that was 8.9 s (easy), 3.4 (snow),
2.3 (obstruction), 15.0 (split), 46.2 (strippy), 8.4 (dark-on-dark) — and the
argmax picked the true family on 2 of 6 probes, because glyph confidence is
not calibrated across families (garbage masks score ~0.7 too).

auto is now a cheap pre-classifier shortlist (`preclass.shortlist`, native
resolution, ~40 ms) and the numbers are in reports/s9-latency.md. These tests
hold the bar so a future edit that quietly re-widens the scan fails loudly.

Pinned here as well: `--family all` still means the old full scan; the
shortlist never exceeds four families and always carries `easy`; auto is
deterministic. The pre-classifier routes — it makes no reading claim.

Run: python3 -m pytest tests/test_auto_latency.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G      # noqa: E402
import preclass as P       # noqa: E402
import typer as T          # noqa: E402

# the official demo probes (tools/demo_latency.py picks), seeds pinned
PROBES = (("easy", 11), ("snow", 12), ("obstruction", 13),
          ("split", 14), ("strippy", 15), ("dark-on-dark", 16))
BAR_S = 10.0

# the five probes the pre-classifier places in the shortlist today; obstruction
# seed 13 is the known miss (reports/s9-latency.md says why and how it behaves:
# it falls back to the easy/safety reading, the same reading the old scan
# returned for that image, in 0.4 s instead of 2.3 s)
ROUTED = ("easy", "snow", "split", "strippy", "dark-on-dark")


def test_auto_stays_under_ten_seconds_on_every_probe():
    worst = (0.0, None)
    for fam, seed in PROBES:
        img, _ = G.generate_one(fam, seed)
        t0 = time.perf_counter()
        T.recognise(img, "auto")
        dt = time.perf_counter() - t0
        if dt > worst[0]:
            worst = (dt, fam)
        assert dt <= BAR_S, (
            f"auto on the {fam} probe took {dt:.1f} s > {BAR_S} s bar "
            f"(full scan was the old behaviour; something re-widened it)")
    assert worst[0] <= BAR_S


def test_shortlist_contains_the_true_family_where_the_classifier_catches():
    for fam, seed in PROBES:
        if fam not in ROUTED:
            continue
        img, _ = G.generate_one(fam, seed)
        short, info = P.shortlist(img)
        assert fam in short, (
            f"{fam} fell out of its own shortlist: {short} ({info})")


def test_auto_family_comes_from_the_shortlist():
    for fam, seed in PROBES:
        img, _ = G.generate_one(fam, seed)
        short, _ = P.shortlist(img)
        _, _, used = T.recognise(img, "auto")
        assert used in short, f"auto read with {used!r}, not in shortlist {short}"


def test_shortlist_is_capped_and_carries_easy():
    for fam, seed in PROBES:
        img, _ = G.generate_one(fam, seed)
        short, _ = P.shortlist(img)
        assert len(short) <= 4, f"shortlist is not capped: {short}"
        assert "easy" in short, f"easy is the safety reading and must ride along: {short}"


def test_full_scan_is_still_available_as_family_all():
    img, _ = G.generate_one("easy", 11)
    short, _ = P.shortlist(img)
    manual = T._best_of(img, T.ALL_FAMILIES)          # what the old auto did
    scan_text, _, scan_fam = T.recognise(img, "all")
    assert (scan_text, scan_fam) == (manual[0], manual[2]), (
        "'all' must still be the full scan (every chain, best confidence)")


def test_auto_is_deterministic():
    img, _ = G.generate_one("easy", 11)
    first = T.recognise(img, "auto")
    second = T.recognise(img, "auto")
    assert (first[0], first[2]) == (second[0], second[2]), (
        "auto returned different readings on the same image")


if __name__ == "__main__":            # script-style too, for tests/run_all.py
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK: auto latency, routing and the full-scan escape hatch hold")
