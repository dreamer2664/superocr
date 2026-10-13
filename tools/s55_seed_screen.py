#!/usr/bin/env python3
"""S55 fresh-seed screen: out-of-sample guard for lex band candidates.

Generates seed-3 suites with the plain floor reader (baseline.read_text,
the same reader as the canonical seed-1 floor receipt), caches the raw rows
to reports/s55_seed3_floor_rows.json, and evaluates the S55 harness
candidates offline on them. Seed 3 appears in no tuning receipt used by
this audit, so it is a genuine out-of-sample screen, not another look at
the data the candidate was selected on.

Usage: python3 tools/s55_seed_screen.py [--seed 3] [--count 10]
(Re-runs are offline once the rows file exists; --regen forces a re-read.)
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--count", type=int, default=10,
                    help="rows per hard family")
    ap.add_argument("--easy-count", type=int, default=100,
                    help="rows for the easy family (canonical suite size)")
    ap.add_argument("--regen", action="store_true")
    args = ap.parse_args()

    rows_path = ROOT / "reports" / f"s55_seed{args.seed}_floor_rows.json"
    if rows_path.exists() and not args.regen:
        rows = json.loads(rows_path.read_text())["rows"]
        print(f"loaded {len(rows)} cached raw rows from {rows_path.name}")
    else:
        import generator as G
        from baseline import read_text
        rows = []
        for fam in G.FAMILIES:
            n = args.easy_count if fam == "easy" else args.count
            for i in range(n):
                img, label = G.generate_one(fam, seed=args.seed, index=i)
                text, _ = read_text(img)
                rows.append({"id": f"{fam}-{i:04d}", "suite":
                             "easy" if fam == "easy" else "hard",
                             "family": fam, "label": label, "got": text})
            print(f"  {fam}: {n} rows", flush=True)
        rows_path.write_text(json.dumps(
            {"seed": args.seed, "count": args.count,
             "easy_count": args.easy_count, "reader": "plain",
             "rows": rows}, indent=1) + "\n")
        print(f"wrote {rows_path.relative_to(ROOT)}")

    from s55_postprocess_harness import CANDIDATES
    by_suite = {"easy": [], "hard": []}
    for r in rows:
        by_suite[r["suite"]].append((r["id"], r["label"], r["got"]))
    base = None
    for name, fn in CANDIDATES.items():
        scores = {s: sum(fn(g) == l for _i, l, g in rs)
                  for s, rs in by_suite.items()}
        if name == "A_shipping":
            base = {r["id"]: fn(r["got"]) for r in rows}
            labels = {r["id"]: r["label"] for r in rows}
            print(f"{name:22s} easy {scores['easy']:3d}  hard {scores['hard']:3d}")
        else:
            alt = {r["id"]: fn(r["got"]) for r in rows}
            fixes = sorted(i for i in labels
                           if alt[i] == labels[i] != base[i])
            breaks = sorted(i for i in labels
                            if base[i] == labels[i] != alt[i])
            print(f"{name:22s} easy {scores['easy']:3d}  hard {scores['hard']:3d}"
                  f"  fixes {fixes} breaks {breaks}")


if __name__ == "__main__":
    main()
