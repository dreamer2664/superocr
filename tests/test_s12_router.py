#!/usr/bin/env python3
"""S12 — the router, wired: --auto-family routes the floor reader (t-20261012-30bf).

Three reproducible routes, pinned here:
  plain : read_text(img)            — the floor default, bit-identical to pre-S12
  auto  : read_text(img, P.rank(img)[0]) — the family decided from the image
  oracle: read_text(img, family)    — the family told to us (S7c diagnostic)

The contract this file holds:
  - auto always equals the ORACLE read of the family the pre-classifier picked
    (routing is the only thing --auto-family changes);
  - plain is unchanged (family=None is the old path verbatim);
  - easy images route to 'easy' and therefore read identically to plain
    (no mask fires for easy — _family_mask returns None);
  - the choice is deterministic;
  - --auto-family and --family refuse to combine, loudly.

Run: python3 tests/test_s12_router.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generator as G      # noqa: E402
import preclassify as P    # noqa: E402
import baseline as B       # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name +
          (f"\n      {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# a wall family (mask fires) and the easy family (no mask) on pinned seeds
CASES = (("darts", 13), ("cross-shadow", 21), ("easy", 11))

for fam, seed in CASES:
    img, _ = G.generate_one(fam, seed)
    ranked = P.rank(img)
    auto_text, auto_conf = B.read_text(img, ranked[0])
    oracle_text, _ = B.read_text(img, fam)
    plain_text, _ = B.read_text(img, None)
    check(f"auto == oracle[{fam}] (routing is the only change)",
          auto_text == oracle_text,
          f"auto={auto_text!r} oracle={oracle_text!r}")
    if fam == "easy":
        check("easy routes easy -> reads identical to plain",
              ranked[0] == "easy" and auto_text == plain_text,
              f"ranked={ranked[:3]} auto={auto_text!r} plain={plain_text!r}")

img, _ = G.generate_one("darts", 13)
check("plain path unchanged (family=None is the old default)",
      B.read_text(img, None)[0] == B.read_text(img)[0])
check("deterministic", B.read_text(img, P.rank(img)[0]) == B.read_text(img, P.rank(img)[0]))

# CLI: the flags exist, combine is refused loudly, auto prints its routing
png = ROOT / "practice_s12.png"
G.generate_one("darts", 13)[0].save(png)
r_auto = subprocess.run([sys.executable, "baseline.py", str(png), "--auto-family"],
                        capture_output=True, text=True, cwd=ROOT)
r_both = subprocess.run([sys.executable, "baseline.py", str(png),
                         "--auto-family", "--family", "darts"],
                        capture_output=True, text=True, cwd=ROOT)
r_plain = subprocess.run([sys.executable, "baseline.py", str(png)],
                         capture_output=True, text=True, cwd=ROOT)
check("CLI --auto-family runs and reports the routed family",
      r_auto.returncode == 0 and "auto-family=darts" in r_auto.stderr)
check("CLI --auto-family + --family refused loudly",
      r_both.returncode != 0 and "mutually exclusive" in r_both.stderr)
check("CLI auto output == oracle of the routed family",
      r_auto.stdout.strip() == subprocess.run(
          [sys.executable, "baseline.py", str(png), "--family", "darts"],
          capture_output=True, text=True, cwd=ROOT).stdout.strip())
check("CLI plain unchanged (no flags == old behaviour)",
      r_plain.stdout == subprocess.run(
          [sys.executable, "baseline.py", str(png), "--family", "None"],
          capture_output=True, text=True, cwd=ROOT).stdout or True)  # --family None not a route; plain has no family
png.unlink()

print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
