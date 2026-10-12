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

# 2) deskew actually de-skews: a rotated clean image must recover.
# t-ac4f: this check moved off the zip-based _char_acc — that metric
# punishes a one-letter length shift as total misalignment (a *better*
# read scored 0.037 against a worse one at 0.148 here). Edit-distance
# ratio measures the intent instead. Measured: base 0.63, rot 0.815.
def _lev_ratio(a: str, b: str) -> float:
    a, b = a.replace(" ", ""), b.replace(" ", "")
    la, lb = len(a), len(b)
    if not max(la, lb):
        return 1.0
    d = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return 1 - d[lb] / max(la, lb)


img, label = G.generate_one("easy", seed=42, index=1)
rot = img.rotate(6.0, fillcolor=(255, 255, 255))
base_acc = _lev_ratio(label, B.read_text(img)[0])
rot_acc = _lev_ratio(label, B.read_text(rot)[0])
check(f"deskew: 6deg rotation keeps >= 80% of the unrotated read "
      f"(edit-distance ratio, was a zip-artifact)",
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
ch, s = B.match_native(g0)
check("native-scale match finds the true small-glyph char", ch == "r",
      f"got {ch!r} score {s:.3f}")

# --- polarity guard (t-20261011-be57): dark-on-dark must not be blind ----
def _ca(label, text):
    l1, l2 = label.replace(" ", ""), text.replace(" ", "")
    tot = max(len(l1), len(l2)) or 1
    return sum(a == b for a, b in zip(l1, l2)) / tot


accs = []
for i in range(10):
    _img, _label = G.generate_one("dark-on-dark", seed=7, index=i)
    _text, _ = B.read_text(_img)
    accs.append(_ca(_label, _text))
mean_acc = sum(accs) / len(accs)
# pre-guard this family averaged 0.000 char (mask was 98% background); the
# guard measured 0.524 on this exact 10-image seed-7 set; image variance is
# wide (0.31 over the first 5), so the bar sits under with real margin.
print(f"polarity guard: dark-on-dark char-acc mean over 10: {mean_acc:.3f}")
if mean_acc < 0.40:
    failures.append("polarity guard regressed: dark-on-dark unreadable again")

# --- wide-glyph rescue (t-20261011-be57): forced-cut merge must not split M's
accs = []
for i in range(10):
    _img, _label = G.generate_one("snow", seed=7, index=i)
    _text, _ = B.read_text(_img)
    accs.append(_ca(_label, _text))
snow_acc = sum(accs) / len(accs)
# pre-rescue snow char was 0.731 on this set (wide glyphs split and read as
# two letters); the forced-cut merge measured 0.960. Bar under with margin.
print(f"wide-glyph rescue: snow char-acc mean over 10: {snow_acc:.3f}")
if snow_acc < 0.85:
    failures.append("wide-glyph rescue regressed: split_wide is halving wide glyphs again")

# --- S8 lever C: rescue re-split + probe matcher (t-20261012-ac4f) -------
accs, ts_ = [], []
for i in range(5):
    _img, _label = G.generate_one("easy", seed=7, index=i)
    _t0 = time.time()
    _text, _ = B.read_text(_img)
    ts_.append(time.time() - _t0)
    accs.append(_ca(_label, _text))
mean_acc, med_s = sum(accs) / len(accs), sorted(ts_)[len(ts_) // 2]
# measured on this set: char 0.809, median 1.6s (bench seed-1: easy 34/100,
# median 1.13s). Bars sit under both with margin.
print(f"S8 lever C: easy char-acc {mean_acc:.3f}, median {med_s:.2f}s over 5")
if mean_acc < 0.70:
    failures.append("S8 rescue re-split regressed easy reads")
if med_s > 8.0:
    failures.append("S8 latency regressed: matcher path over 8s median")

print(f"\n({time.time() - t0:.0f}s total)")
if failures:
    print("FAILURES:", len(failures))
    for _f in failures:
        print(" -", _f)
    sys.exit(1)
print("OK: the floor is honest, deskewed, deterministic, and metrics-fixed")
