#!/usr/bin/env python3
"""s10b_probe.py — bench-compatible reader CLI for an S10b glyph policy.

Prints the read text for one image so bench.py can score a policy against the
official suites with the official protocol:

  python3 bench.py --suite-dir /tmp/s10-suites --runs 1 \
    --reader "python3 tools/s10b_probe.py --policy cnn --image {image}"

Policies and their meaning are in tools/s10b_gate.py. `--policy floor` must
print exactly what `python3 baseline.py <image>` prints; `--check` asserts
that against the real chain before reading, so a drifted mirror fails loudly
instead of producing a number nobody can reproduce.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from s10b_gate import Net, read_text_with, verify_mirror  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="S10b glyph-policy probe (S10b)")
    ap.add_argument("--image", required=True)
    ap.add_argument("--policy", choices=("floor", "gate", "cnn"), default="floor")
    ap.add_argument("--gate", type=float, default=0.9)
    ap.add_argument("--min-prob", type=float, default=0.5)
    ap.add_argument("--weights", default=None)
    ap.add_argument("--check", action="store_true",
                    help="verify the mirror against baseline.read_text first")
    args = ap.parse_args()

    with Image.open(args.image) as im:
        im = im.convert("RGB")
        if args.check:
            chain, mirror = verify_mirror(im)
            if chain != mirror:
                print(f"s10b_probe: mirror drifted from baseline.read_text: "
                      f"{chain!r} vs {mirror!r}", file=sys.stderr)
                return 3
        net = None if args.policy == "floor" else Net(args.weights)
        text = read_text_with(im, policy=args.policy, gate=args.gate,
                              min_prob=args.min_prob, net=net)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
