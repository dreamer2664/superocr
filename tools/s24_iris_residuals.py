#!/usr/bin/env python3
"""S24 (t-20261012-c4af, marcus): classify the 10 non-corrosion iris hard residuals.

Input: the residual list pericles published on the bus 20:33Z (iris-lex run-1,
hard 84/100). The true label lines come from the canonical seed-1 suite
manifest; the "got" lines below are SIMULATED from his per-item fragments
(the real model reads live in his run logs). If the real got lines differ,
feed them via --jsonl '{"id": ..., "got": ...}' lines and the classification
recomputes.

For every item: apply the merged post-pass (tools/lex_projection.fix_line,
R1-R5 at main) to the full got line and compare to the true label.

Run:  python3 tools/s24_iris_residuals.py [--jsonl FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lex_projection import fix_line  # noqa: E402

# (item, true label [seed-1 manifest], simulated got [pericles' fragments])
RESIDUALS = [
    ("cut-0002",         "TrAIL fennel FLINT",       "TrAiL fennel FLINT"),
    ("cut-0006",         "torque DrIfT OBSIdiAN",    "torque DrIfT OBSidiÁN"),
    ("darts-0001",       "ORCHID fAlCOn",            "ORCHID fAlC0n"),
    ("obstruction-0001", "FlINT plume",              "FLINT plume"),
    ("obstruction-0003", "MOss Fjord",               "M0ss Fjord"),
    ("snow-0007",        "gLAcier bRoOk 002 Indigo", "gLAcier bRo0k 002 Indigo"),
    ("split-0001",       "Comet MEriDIAn",           "Comet MERiDiAn"),
    ("stitch-0007",      "COPPER 008 linen",         "COPPER 0 08 linen"),
    ("strippy-0003",     "falcON 005 GLACIER",       "falc0N 005 GLACIER"),
    ("strippy-0004",     "lUpIne Cedar",             "lupine Cedar"),
]


def classify(label: str, out: str, got: str) -> str:
    """Lane for the residual after the merged post-pass has done its best."""
    if out == label:
        return "FIXED-BY-POSTPASS"
    lo = lambda s: s.lower()  # noqa: E731
    if lo(out) == lo(label):
        # letters all correct after projection; only case differs
        if lo(got) == lo(label):
            return "CASE-ONLY (model misread case; lex-immune by R1)"
        return "CASE-AT-REPAIRED-POSITION (projection fixed letters, case coin-flip lost)"
    if "".join(got.split()) == "".join(label.split()) and got != label:
        return "SPACING (digit-token split; no safe post-pass rejoin)"
    return "OTHER (letters still wrong after projection)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", help="file of {\"id\":..., \"got\":...} real model reads")
    a = ap.parse_args()

    got_by_id = {}
    if a.jsonl:
        for line in open(a.jsonl):
            line = line.strip()
            if line:
                r = json.loads(line)
                got_by_id[r["id"]] = r["got"]

    n_fixed = 0
    rows = []
    for item, label, got_sim in RESIDUALS:
        got = got_by_id.get(item, got_sim)
        src = "log" if item in got_by_id else "sim"
        out = fix_line(got)
        lane = classify(label, out, got)
        n_fixed += out == label
        rows.append((item, src, got, out, label, lane))

    w = max(len(r[0]) for r in rows)
    for item, src, got, out, label, lane in rows:
        print(f"{item:<{w}} [{src}] got={got!r} -> out={out!r}")
        print(f"{'':<{w}}       label={label!r}  lane: {lane}")
    print(f"\npost-pass repairs to exact: {n_fixed}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
