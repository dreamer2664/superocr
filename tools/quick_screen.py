#!/usr/bin/env python3
"""quick_screen — per-family quick screen (t-20261014-5830, S74).

NOT A BENCH. This is the 1-2 minute feedback loop for work in progress:
generate N items per family at an explicit seed, read them with the
chosen reader route, print a per-family table and write a JSON. The only
source of headline numbers is bench.py on the canonical suites (BENCH.md);
anything this tool prints is a SCREEN, not proof.

Usage:
  python3 tools/quick_screen.py                       # 10/family, seed 901, plain
  python3 tools/quick_screen.py --seed 902 --count 5 --reader lex
  python3 tools/quick_screen.py --families corrosion,strippy

Determinism: generator + readers are deterministic per (family, seed,
index); the same command prints the same table (asserted by tests).
Seeds default to >= 900 and must not be 1/2/3/4/53 (canonical, eval-only).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

BANNER = ("=========================================================\n"
          "  SCREEN, not proof — never a headline number.\n"
          "  Quick per-family feedback only. Headline numbers come\n"
          "  from bench.py on the canonical suites (see BENCH.md).\n"
          "=========================================================")
FORBIDDEN_SEEDS = {1, 2, 3, 4, 53}     # canonical / frozen — eval-only
DEFAULT_SEED = 901


def read_with(route: str, img):
    """Read one image through the chosen route. 'plain' = baseline floor,
    'lex' = floor + shipping lex projection (reader_lex semantics)."""
    if route == "plain":
        import baseline as B
        text, _conf = B.read_text(img, None)
        return text
    if route == "lex":
        import baseline as B
        from lex_projection import fix_line
        text, _conf = B.read_text(img, None)
        return fix_line(text)
    raise ValueError(f"unknown reader route: {route!r} (plain | lex)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help=f"generation seed (default {DEFAULT_SEED}; "
                         "never 1/2/3/4/53)")
    ap.add_argument("--count", type=int, default=10,
                    help="items per family (default 10)")
    ap.add_argument("--reader", choices=["plain", "lex"], default="plain")
    ap.add_argument("--families", default="",
                    help="comma-separated subset (default: all)")
    ap.add_argument("--out", default="",
                    help="write JSON here (default: no file)")
    ap.add_argument("--quiet", action="store_true",
                    help="banner still prints; suppress per-item lines")
    args = ap.parse_args()

    if args.seed in FORBIDDEN_SEEDS:
        print(f"refusing seed {args.seed}: canonical/frozen seeds are "
              "evaluation-only (BENCH.md). Use a fresh seed (>=900 "
              "recommended).", file=sys.stderr)
        return 2
    if args.count < 1:
        print("--count must be >= 1", file=sys.stderr)
        return 2

    import generator as G
    families = ([f.strip() for f in args.families.split(",") if f.strip()]
                or list(G.FAMILIES))
    unknown = [f for f in families if f not in G.FAMILIES]
    if unknown:
        print(f"unknown families: {unknown}; valid: {list(G.FAMILIES)}",
              file=sys.stderr)
        return 2

    print(BANNER)
    print(f"seed {args.seed} · {args.count}/family · reader "
          f"{args.reader} · families {len(families)}")

    rows = []
    t0 = time.perf_counter()
    for fam in families:
        hits = 0
        for i in range(args.count):
            img, label = G.generate_one(fam, seed=args.seed, index=i)
            got = read_with(args.reader, img)
            exact = got == label
            hits += exact
            rows.append({"id": f"{fam}-{i:04d}", "family": fam,
                         "seed": args.seed, "index": i, "label": label,
                         "got": got, "exact": exact})
            if not args.quiet:
                mark = "=" if exact else "X"
                print(f"  [{mark}] {fam}-{i:04d} {label!r} -> {got!r}")
        print(f"  {fam:14s} {hits:3d}/{args.count:<3d}")
    wall = time.perf_counter() - t0

    hits = sum(r["exact"] for r in rows)
    print(f"  {'SCREEN-total':14s} {hits:3d}/{len(rows):<3d}   "
          f"({wall:.1f}s wall)")
    print("  SCREEN, not proof — never a headline number.")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"tool": "quick_screen", "banner": "SCREEN, not proof — "
             "never a headline number", "seed": args.seed,
             "count_per_family": args.count, "reader": args.reader,
             "families": families, "wall_s": round(wall, 2),
             "screen_total": [hits, len(rows)], "rows": rows}, indent=1)
            + "\n")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
