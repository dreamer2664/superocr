#!/usr/bin/env python3
"""S70 held-out screens: instrument on seed-5/6 (v2 protocol).

STATUS: NEVER RUN — the v2 gate NO-GO'd (1 regression, easy-0009)
before the held-out stage, per the protocol's order. Committed for a
future v3; the gate receipts and the final report are the record.

For every committed seed-5/6 screen row (S72, PR #94): regenerate the
image deterministically (generator.generate_one, same (family, seed,
index) the rows were built with), take the committed raw floor read,
apply the shipping route (fix_line), then the case instrument, and
compare. Zero-regression baseline = the committed shipping_lex rows.

Usage: python3 tools/s70_held_out.py            # both seeds
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import generator as G                     # noqa: E402
from lex_projection import fix_line       # noqa: E402
from s70_case_instrument import correct_cases  # noqa: E402


def run_seed(seed: int) -> None:
    rows = json.loads(
        (ROOT / f"reports/s55_seed{seed}_floor_rows.json").read_text()
    )["rows"]
    screen = {}
    for line in (ROOT / f"reports/screens/seed{seed}.jsonl").read_text()\
            .splitlines():
        d = json.loads(line)
        screen[d["id"]] = d
    tot = fix_n = brk_n = 0
    base_ex = inst_ex = 0
    for r in rows:
        img, label = G.generate_one(r["family"], seed=seed,
                                    index=int(r["id"].rsplit("-", 1)[1]))
        shipping = fix_line(r["got"])                 # committed raw + lex
        with_instr = correct_cases(img, shipping)
        base_ok = screen[r["id"]]["shipping_exact"]
        inst_ok = with_instr == r["label"]
        tot += 1
        base_ex += base_ok
        inst_ex += inst_ok
        if inst_ok and not base_ok:
            fix_n += 1
            print(f"  FIX  {r['id']}: {shipping!r} -> {with_instr!r}")
        if base_ok and not inst_ok:
            brk_n += 1
            print(f"  BRK  {r['id']}: {shipping!r} -> {with_instr!r}"
                  f" (label {r['label']!r})")
    print(f"seed-{seed}: {tot} rows | committed shipping exact {base_ex} | "
          f"+instrument exact {inst_ex} | fixes {fix_n} breaks {brk_n}")


def main() -> int:
    for seed in (5, 6):
        run_seed(seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
