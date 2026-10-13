#!/usr/bin/env python3
"""Tests for the S39 latency memoization (t-20261013-cbe7).

The optimizations must be INVISIBLE: same reads, same scores, same order.
These tests pin exactly that — cache round-trip equality, corrupt-cache
fallback, sort-cache equivalence, and trim bit-identity. Script-style:
run it, exit 0 iff all checks pass. Offline, seeded, fast.

    python3 tests/test_s39_template_cache.py
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import baseline as B  # noqa: E402
import reader as R  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name +
          (f"\n      {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


t0 = time.time()

# 1) cache round-trip: whatever _templates_native returns (disk or fresh
#    render) must equal a direct fresh render, key-for-key in the same order.
NOM = 11
fresh = B._render_templates_native(NOM)
cached = B._templates_native(NOM)
check("template cache round-trip: same keys, same order",
      list(cached.keys()) == list(fresh.keys()),
      f"{len(cached)} vs {len(fresh)} keys")
check("template cache round-trip: masks bit-identical",
      all(np.array_equal(cached[k], fresh[k]) for k in fresh))

# 2) the cache file exists after the call and re-loads to the same content
#    (proves the disk path actually served/stored, not just memory).
stamp = B._tcache_stamp()
path = B._TCACHE_DIR / f"t-{stamp}-{NOM}.pkl"
check("cache file written under .template-cache/", path.exists(), str(path))
if path.exists():
    import pickle
    with open(path, "rb") as fh:
        on_disk = pickle.load(fh)
    check("on-disk masks bit-identical to fresh render",
          list(on_disk.keys()) == list(fresh.keys())
          and all(np.array_equal(on_disk[k], fresh[k]) for k in fresh))

# 3) corrupt cache -> silent fallback to rendering, identical result.
NOM2 = 13
B._templates_native(NOM2)  # ensure the file exists
path2 = B._TCACHE_DIR / f"t-{stamp}-{NOM2}.pkl"
good = B._templates_native(NOM2)
if path2.exists():
    path2.write_bytes(b"not a pickle at all")
    B._templates_native.cache_clear()
    recovered = B._templates_native(NOM2)
    check("corrupt cache file: fallback render, bit-identical",
          list(recovered.keys()) == list(good.keys())
          and all(np.array_equal(recovered[k], good[k]) for k in good))
    check("corrupt cache file: healed on disk",
          path2.exists() and path2.stat().st_size > 32)

# 4) _sorted_cands must equal the inline sort it replaced, element order and
#    identity (the three match sites depend on this exact sequence).
for h in (17, 23):
    direct = sorted(B._cands_for_height(h),
                    key=lambda cf: (abs(cf[2].shape[0] - h), cf[1]))
    cached_sorted = B._sorted_cands(h)
    check(f"_sorted_cands(h={h}) order identical to inline sorted()",
          len(direct) == len(cached_sorted)
          and all(a[0] == b[0] and a[1] == b[1] and a[2] is b[2]
                  for a, b in zip(direct, cached_sorted)))

# 5) trim: new projection implementation == old np.where semantics.
rng = np.random.default_rng(39)
old_ok = True
for trial in range(200):
    hgt, wid = int(rng.integers(1, 9)), int(rng.integers(1, 9))
    m = rng.random((hgt, wid)) < float(rng.integers(0, 3)) / 2.0
    ys, xs = np.where(m)
    if len(xs) == 0:
        want = m
    else:
        want = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    got = R.trim(m)
    if got.shape != want.shape or not np.array_equal(got, want):
        old_ok = False
        break
check("trim: projection version bit-identical to np.where version (200 trials)",
      old_ok)
empty = np.zeros((4, 4), bool)
check("trim: empty mask returned unchanged", R.trim(empty) is empty or
      np.array_equal(R.trim(empty), empty))

# 6) end-to-end smoke: a generated easy image reads the same through the
#    public API before/after semantics (deterministic generator, fixed seed).
import generator as G  # noqa: E402
img, label = G.generate_one("easy", seed=7, index=0)
text, _ = B.read_text(img)
check("read_text smoke on seeded easy image returns non-empty text",
      bool(text), f"label={label!r} got={text!r}")

print(f"\n{len(failures)} failure(s), {time.time() - t0:.1f}s")
sys.exit(1 if failures else 0)
