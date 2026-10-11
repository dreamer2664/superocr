#!/usr/bin/env python3
"""make_suites.py — build the bench suites from generator.py, deterministically.

t-20261011-b0cb (S5, the three-run proof). bench.py (S0) scores whatever sits
in data/<suite>/ in the BENCH.md format; this script is what puts it there:

    data/easy/manifest.jsonl   + images/<id>.png   (the plain family)
    data/hard/manifest.jsonl   + images/<id>.png   (12 families, balanced)

The ids carry the family (<family>-<nnnn>) so a per-image adapter can route an
image without parsing the manifest (tools/bench_adapter.py does exactly that).

Determinism is the point: same --seed -> byte-identical suites. --check builds
the suites twice into two temp dirs, compares them file-for-file, and validates
the result with `bench.py --validate`. data/ is git-ignored on purpose
(JOBS.md: datasets are generated, not committed).

Usage:
    python3 tools/make_suites.py                        # 100 easy + 100 hard, seed 1
    python3 tools/make_suites.py --easy 12 --hard 12 --seed 1 --out /tmp/data
    python3 tools/make_suites.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import generator as G  # noqa: E402

EASY_FAMILY = "easy"
HARD_FAMILIES = [f for f in G.FAMILIES if f != EASY_FAMILY]  # 12, generator order


def build_suite(suite: str, count: int, seed: int, out: Path) -> list[dict]:
    rows = []
    for i in range(count):
        if suite == "easy":
            fam, idx = EASY_FAMILY, i
        else:
            fam = HARD_FAMILIES[i % len(HARD_FAMILIES)]
            idx = i // len(HARD_FAMILIES)  # per-family index, same count each
        img, label = G.generate_one(fam, seed, idx)
        item_id = f"{fam}-{idx:04d}"
        rel = f"images/{item_id}.png"
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, format="PNG")
        rows.append({"id": item_id, "image": rel, "label": label, "family": fam,
                     "tags": ["seeded", f"seed={seed}"]})
    return rows


def write_suite(suite: str, count: int, seed: int, root: Path) -> dict:
    suite_dir = root / suite
    rows = build_suite(suite, count, seed, suite_dir)
    with open(suite_dir / "manifest.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"suite": suite, "items": len(rows), "seed": seed,
            "families": sorted({r["family"] for r in rows}),
            "dir": str(suite_dir)}


def dir_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--easy", type=int, default=100, help="easy items (default 100)")
    ap.add_argument("--hard", type=int, default=100, help="hard items (default 100)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "data"),
                    help="suite root (default <repo>/data)")
    ap.add_argument("--check", action="store_true",
                    help="build twice into temp dirs, compare, validate; write nothing")
    args = ap.parse_args(argv)

    if args.check:
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            a, b = Path(t1), Path(t2)
            for root in (a, b):
                for suite, count in (("easy", args.easy), ("hard", args.hard)):
                    write_suite(suite, count, args.seed, root)
            ha, hb = dir_hash(a), dir_hash(b)
            if ha != hb:
                print(f"FAIL: not deterministic ({ha[:12]} != {hb[:12]})", file=sys.stderr)
                return 1
            bench = ROOT / "bench.py"
            if bench.exists():
                p = subprocess.run([sys.executable, str(bench), "--suite-dir", str(a),
                                    "--validate"], capture_output=True, text=True)
                if p.returncode != 0:
                    print("FAIL: bench.py --validate rejected the suites:\n"
                          + (p.stdout + p.stderr).strip(), file=sys.stderr)
                    return 1
                print(f"OK: two builds identical ({ha[:12]}), bench.py --validate green")
            else:
                print(f"OK: two builds identical ({ha[:12]}); bench.py not present, skipped validate")
        return 0

    out = Path(args.out)
    reports = [write_suite("easy", args.easy, args.seed, out),
               write_suite("hard", args.hard, args.seed, out)]
    for r in reports:
        fams = len(r["families"])
        print(f"{r['suite']:5s}: {r['items']:4d} items, {fams:2d} families, "
              f"seed {r['seed']} -> {r['dir']}")
    print(f"suite hash: {dir_hash(out)[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
