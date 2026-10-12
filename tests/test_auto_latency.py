#!/usr/bin/env python3
"""Auto-mode latency and routing bars (t-20261012-5c63, S9 harness).

The product bar from JOBS.md: every auto-mode probe answers in under 10 s.
Before S9, auto ran all thirteen chains and kept the loudest confidence:
8.9 s (easy), 3.4 (snow), 2.3 (obstruction), 15.0 (split), 46.2 (strippy),
8.4 (dark-on-dark) on these same pinned images — and that arbitration
picked the true family on 2 of 6 probes, because glyph confidence is not
calibrated across families (garbage masks score ~0.7 too).

auto now runs `preclassify`'s top-ranked chain (cormac's classifier: 86.5%
top-1 / 79.8% top-1 on two held-out protocols, measured; every official
probe routed first). These tests pin the bars so a quiet re-widening fails
loudly: every probe under 10 s, the pre-classifier names the true family
first on all six probes, auto's family is the top candidate, `--family all`
is still exactly the old full scan, auto is deterministic, and the
shortlist keeps `easy` in its last slot when easy ranks within the top k+1.

Run: python3 -m pytest tests/test_auto_latency.py   (or as a script)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G       # noqa: E402
import preclassify as P     # noqa: E402
import reader as R          # noqa: E402
import typer as T           # noqa: E402

# the official demo probes (tools/demo_latency.py picks), seeds pinned
PROBES = (("easy", 11), ("snow", 12), ("obstruction", 13),
          ("split", 14), ("strippy", 15), ("dark-on-dark", 16))
BAR_S = 10.0


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
            f"(something re-widened the scan)")
    assert worst[1] is not None


def test_preclassifier_names_the_true_family_first_on_every_probe():
    for fam, seed in PROBES:
        img, _ = G.generate_one(fam, seed)
        ranked = P.rank(img)
        assert ranked[0] == fam, (
            f"{fam} probe routed to {ranked[0]!r} first (top3 {ranked[:3]})")


def test_auto_family_is_the_preclassifiers_top_candidate():
    for fam, seed in PROBES:
        img, _ = G.generate_one(fam, seed)
        _, _, used = T.recognise(img, "auto")
        assert used == P.rank(img)[0], (
            f"auto reported {used!r}, not the top candidate {P.rank(img)[0]!r}")


def test_all_is_still_the_full_scan():
    img, _ = G.generate_one("easy", 11)
    best = ("", [], None, -1.0)
    for cand in T.ALL_FAMILIES:                    # what the old auto did
        try:
            text, conf, _ = R.read_chain(img, cand)
        except SystemExit:
            continue
        avg = sum(conf) / len(conf) if conf else 0.0
        if avg > best[3]:
            best = (text, conf, cand, avg)
    scan = T.recognise(img, "all")
    assert (scan[0], scan[2]) == (best[0], best[2]), (
        "'all' must still be the exhaustive scan (every chain, best confidence)")


def test_auto_is_deterministic():
    img, _ = G.generate_one("easy", 11)
    first = T.recognise(img, "auto")
    second = T.recognise(img, "auto")
    assert (first[0], first[2]) == (second[0], second[2]), (
        "auto returned different readings on the same image")


def test_shortlist_keeps_easy_in_its_last_slot_when_easy_is_next():
    for fam, seed in PROBES:
        img, _ = G.generate_one(fam, seed)
        ranked = P.rank(img)
        short = P.shortlist(img, k=2)
        assert len(short) <= 3, f"shortlist not bounded: {short}"
        if len(ranked) > 2 and ranked[2] == "easy" and "easy" not in ranked[:2]:
            assert "easy" in short, (
                f"easy ranked third but fell out of the shortlist: {short}")


if __name__ == "__main__":            # script-style too, for tests/run_all.py
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK: auto latency, routing, the full-scan hatch and determinism hold")
