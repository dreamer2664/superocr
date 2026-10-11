#!/usr/bin/env python3
"""Tests for the classic baseline (t-20261011-65ff). Script-style: run it,
exit 0 iff all checks pass. Offline, seeded, deterministic.

    python3 tests/test_baseline.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import baseline as B  # noqa: E402
import generator as G  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name +
          (f"\n      {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


t0 = time.time()

# 1) the floor on easy: measured numbers must hold (floor, not a promise)
N, SEED = 8, 7
exact = cok = 0
for i in range(N):
    img, label = G.generate_one("easy", seed=SEED, index=i)
    text, _ = B.read_text(img)
    exact += text == label
    cok += B._char_acc(label, text)
check(f"easy floor: char accuracy >= 0.60 (measured 0.72 at n=20)",
      cok / N >= 0.60, f"got {cok / N:.2f}")
check(f"easy floor: at least one exact read in {N}", exact >= 1,
      f"exact {exact}/{N}")

# 2) deskew actually de-skews: a rotated clean image must recover
img, label = G.generate_one("easy", seed=42, index=1)
rot = img.rotate(6.0, fillcolor=(255, 255, 255))
base_acc = B._char_acc(label, B.read_text(img)[0])
rot_acc = B._char_acc(label, B.read_text(rot)[0])
check(f"deskew: 6deg rotation keeps >= 80% of the unrotated read",
      rot_acc >= 0.8 * base_acc, f"base {base_acc:.2f} -> rot {rot_acc:.2f}")

# 3) determinism: same seed, same sweep, byte-identical JSON
r1 = B.score_all(2, 99, ["easy", "snow", "split"])
r2 = B.score_all(2, 99, ["easy", "snow", "split"])
check("score_all is deterministic", json.dumps(r1, sort_keys=True)
      == json.dumps(r2, sort_keys=True))

# 4) reference pack: exactly the scored tiles are measured, '?' never guessed
ref = B.score_reference()
check("reference measures exactly the 26 scored tiles", ref["measured"] == 26,
      str(ref["measured"]))
check("reference excludes exactly the 6 '?' tiles", ref["excluded"] == 6,
      str(ref["excluded"]))
excluded_ids = {e["id"] for e in ref["excluded_tiles"]}
check("excluded tiles are named, never measured", excluded_ids and
      all(e["id"] not in {m["id"] for m in ref["per_tile"]} for e in ref["excluded_tiles"]))

# 5) native-scale matcher is the metrics fix: a face's own render must be found
#    at native scale (the 10x10 DejaVuSerif-Bold 'r' case from the PR notes)
img, label = G.generate_one("easy", seed=SEED, index=0)
import PIL.ImageOps as ImageOps
mask = __import__("reader").trim(__import__("reader").despeck(__import__("reader").otsu(
    np.array(ImageOps.autocontrast(img.convert("L"), cutoff=0), dtype=np.float32))))
g0 = __import__("reader").split_wide(__import__("reader").trim(mask[:, 0:10]))[0]
ch, s = B.match_native(g0, 15)  # cap height of the word 'raVen' is 15 (the 'V')
check("native-scale match finds the true small-glyph char", ch == "r",
      f"got {ch!r} score {s:.3f}")

print(f"\n({time.time() - t0:.0f}s total)")
if failures:
    print("FAILURES:", len(failures))
    sys.exit(1)
print("OK: the floor is honest, deskewed, deterministic, and metrics-fixed")
