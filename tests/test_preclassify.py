#!/usr/bin/env python3
"""Tests for the auto-mode pre-classifier (t-20261012-5c63). Script-style:
run it, exit 0 iff all checks pass. Offline, seeded, deterministic — no
network, no GPU, nothing but the repo's own generator.

What is tested (and why it is the honest version of each claim):
  1. held-out accuracy of the shortlist (images the centroids never saw),
  2. determinism: rank() is stable, and --rebuild reproduces the committed
     centroid cache byte-for-value,
  3. auto mode reads an image exactly like the pinned family when the
     pre-classifier is right (same chain, same text),
  4. latency: every demo family's auto read finishes well under the 10 s
     bar, in-process (the server adds its own overhead, measured separately
     by tools/demo_latency.py),
  5. the CLI entry point works on a saved PNG.

    python3 tests/test_preclassify.py
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generator as G  # noqa: E402
import preclassify as P  # noqa: E402
import typer as T  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name +
          (f"\n      {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


t0 = time.time()

# 1) held-out shortlist accuracy (the documented bar: top-2 >= 90%)
DEMO = (("easy", 11), ("snow", 12), ("obstruction", 13),
        ("split", 14), ("strippy", 15), ("dark-on-dark", 16))
top1 = top2 = n = 0
for fam in P.ALL_FAMILIES:
    for idx in P.HELDOUT_INDICES:
        ranked = P.rank(G.generate_one(fam, seed=P.SEED, index=idx)[0])
        top1 += ranked[0] == fam
        top2 += fam in ranked[:2]
        n += 1
check(f"held-out top-1 >= 75% (measured 87%)", top1 / n >= 0.75, f"got {top1}/{n}")
check(f"held-out top-2 >= 90% (measured 94%)", top2 / n >= 0.90, f"got {top2}/{n}")
print(f"      held-out: top-1 {top1}/{n} ({top1 / n:.0%}), "
      f"top-2 {top2}/{n} ({top2 / n:.0%})")

# 2) determinism
img, _ = G.generate_one("split", seed=14)
r1, r2 = P.rank(img), P.rank(img)
check("rank() is deterministic", r1 == r2)
fresh = P.build_centroids()
cached = P.load_centroids()
same = all(np.array_equal(fresh[f], cached[f]) for f in P.ALL_FAMILIES)
check("committed cache == fresh rebuild (same seed)", same,
      "delete models/preclass_centroids.npz and run: python3 preclassify.py --rebuild")

# 3) auto == pinned when the pre-classifier is right
for fam, seed in DEMO:
    im, _ = G.generate_one(fam, seed)
    at, ac, af = T.recognise(im, "auto")
    pt, pc, pf = T.recognise(im, fam)
    check(f"auto == pinned on demo probe {fam} (seed {seed})",
          (at, af) == (pt, pf), f"auto chose {af!r}, pinned is {pf!r}")

# 4) latency: every demo family, in-process, must be far under the 10 s bar
BAR = 10.0
for fam, seed in DEMO:
    im, _ = G.generate_one(fam, seed)
    t = time.perf_counter()
    T.recognise(im, "auto")
    dt = time.perf_counter() - t
    check(f"auto latency {fam} < {BAR:.0f}s (measured <1s)", dt < BAR, f"took {dt:.1f}s")

# 5) CLI entry point on a saved PNG
with tempfile.TemporaryDirectory() as d:
    png = Path(d) / "probe.png"
    G.generate_one("strippy", 15)[0].save(png)
    out = subprocess.run([sys.executable, "preclassify.py", str(png), "--top", "3"],
                         capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent)
    check("CLI: python3 preclassify.py probe.png --top 3",
          out.returncode == 0 and "strippy" in out.stdout,
          out.stdout + out.stderr)

print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}"
      f"  ({time.time() - t0:.1f}s)")
sys.exit(1 if failures else 0)
