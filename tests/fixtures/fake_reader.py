#!/usr/bin/env python3
"""fake_reader.py — a deliberately simple stand-in for a real reader.

Used only by tests/test_bench.py to exercise the bench mechanics (scoring,
gallery, errors, timeouts, stability). It knows nothing about images: it looks
the answer up in a JSON map keyed by the image basename, so tests stay
stdlib-only and fast.

Modes:
    ok        print the mapped text (the "correct" answer)
    wrong     print the mapped text with an X glued on
    space     print the mapped text plus a trailing space (must MISS: exactness)
    crash     write to stderr and exit 3 (a failed item, not a bench crash)
    sleep     sleep --sleep seconds, then print the mapped text (timeout test)
    stateful  keep a counter in --state, incremented on every read it serves
              (items within a run, runs within a --runs N batch); the read whose
              count equals --fail-on prints the wrong text — so exactly one
              invocation fails, and the stability test can aim it at one run
"""

import argparse
import json
import os
import sys
import time


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--map", required=True)
    p.add_argument("--mode", default="ok")
    p.add_argument("--state", default=None)
    p.add_argument("--fail-on", type=int, default=0)
    p.add_argument("--sleep", type=float, default=0.0)
    args = p.parse_args()

    with open(args.map, encoding="utf-8") as fh:
        mapping = json.load(fh)
    key = os.path.splitext(os.path.basename(args.image))[0]
    text = mapping.get(key)
    if text is None:
        print(f"fake_reader: no entry for {key}", file=sys.stderr)
        return 4

    if args.mode == "crash":
        print("fake_reader: crashing on purpose", file=sys.stderr)
        return 3
    if args.mode == "sleep":
        time.sleep(args.sleep)
        print(text)
        return 0
    if args.mode == "stateful":
        count = 0
        if args.state and os.path.exists(args.state):
            with open(args.state, encoding="utf-8") as fh:
                count = int(fh.read().strip() or "0")
        count += 1
        if args.state:
            with open(args.state, "w", encoding="utf-8") as fh:
                fh.write(str(count))
        if args.fail_on and count == args.fail_on:
            print(text + "WRONG")
            return 0
        print(text)
        return 0
    if args.mode == "wrong":
        print(text + "X")
        return 0
    if args.mode == "space":
        print(text + " ")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
