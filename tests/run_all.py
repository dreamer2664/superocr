#!/usr/bin/env python3
"""run_all.py — run every test in tests/, whatever style it is written in.

Why this exists (t-20261011-2f3d): the project's checks are written by several
agents. Some are unittest classes; others are script-style files with their own
`def main()`/`sys.exit`. `python3 -m pytest` collects none of the script-style
ones, and `python3 -m unittest discover` collects none of them either — and
since Python 3.12 an empty test run exits 5, so CI does not fail honestly, it
fails confusingly (or passes vacuously on older runners). A green tick that
means nothing is exactly what this project must not have.

This runner executes each tests/test_*.py as a subprocess and reports per-file
status and timing. A file passes iff it exits 0. It works for both styles and
needs nothing but the standard library.

    python3 tests/run_all.py                 # everything
    python3 tests/run_all.py --only bench    # files whose name contains 'bench'
    python3 tests/run_all.py --list          # what would run, then exit

Exit codes: 0 = all files passed (or none exist yet), 1 = at least one failed,
2 = misuse.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def find_tests(only: str | None = None) -> list[Path]:
    found = sorted(p for p in HERE.glob("test_*.py") if p.is_file())
    if only:
        found = [p for p in found if only in p.name]
    return found


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", default=None, help="only files whose name contains this")
    p.add_argument("--list", action="store_true", help="list what would run")
    p.add_argument("--timeout", type=float, default=600.0,
                   help="per-file timeout in seconds (default: 600)")
    args = p.parse_args()

    files = find_tests(args.only)
    if args.list:
        for f in files:
            print(f.relative_to(ROOT))
        return 0
    if not files:
        print("NO TESTS FOUND under tests/ — this is a notice, not a pass "
              "(the first S0 task brings them; see JOBS.md)")
        return 0

    failures: list[tuple[str, str]] = []
    total_started = time.perf_counter()
    for path in files:
        rel = path.relative_to(ROOT)
        started = time.perf_counter()
        try:
            proc = subprocess.run([sys.executable, str(path)],
                                  cwd=str(ROOT), capture_output=True, text=True,
                                  timeout=args.timeout)
            seconds = time.perf_counter() - started
            if proc.returncode == 0:
                print(f"PASS  {rel}  ({seconds:.2f}s)")
            else:
                print(f"FAIL  {rel}  (exit {proc.returncode}, {seconds:.2f}s)")
                tail = (proc.stdout + proc.stderr).strip().splitlines()[-12:]
                for line in tail:
                    print(f"      {line}")
                failures.append((str(rel), f"exit {proc.returncode}"))
        except subprocess.TimeoutExpired:
            print(f"FAIL  {rel}  (timeout after {args.timeout:g}s)")
            failures.append((str(rel), "timeout"))

    total = time.perf_counter() - total_started
    print()
    if failures:
        print(f"{len(files) - len(failures)}/{len(files)} files passed "
              f"({total:.2f}s); failing: {', '.join(name for name, _ in failures)}")
        return 1
    print(f"{len(files)}/{len(files)} files passed ({total:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
