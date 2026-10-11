#!/usr/bin/env python3
"""bench_adapter.py — route one bench image to a family-aware reader (S5).

bench.py hands a reader exactly one image path (plus an id it cannot always
use). Some readers need more: read.py dispatches on the family, a CNN does not
care. make_suites.py encodes the family in the file stem ("<family>-<nnnn>"),
so this adapter derives it from the path and substitutes {image}/{family} into
whatever inner command you give it:

    --reader "python3 tools/bench_adapter.py {image}"
    --reader "python3 tools/bench_adapter.py {image} --cmd 'python3 readers/cnn_reader.py {image}'"

The inner command's stdout/exit code pass through untouched; a failure is a
failed item to bench.py (with the error text), never a bench crash. The default
inner command is the repo's family reader: `python3 reader.py <image> --family <fam>`.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def family_of(image: str) -> str:
    stem = Path(image).stem
    fam = stem.rsplit("-", 1)[0] if "-" in stem else stem
    return fam or "easy"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image", help="the image bench.py handed us")
    ap.add_argument("--cmd", default=None,
                    help="inner command template with {image} and/or {family}; "
                         "default: reader.py --family")
    ap.add_argument("--print-family", action="store_true",
                    help="print the derived family and exit (debugging)")
    args = ap.parse_args(argv)

    fam = family_of(args.image)
    if args.print_family:
        print(fam)
        return 0
    if args.cmd:
        parts = shlex.split(args.cmd)
        if not any("{image}" in p or "{family}" in p for p in parts):
            parts.append(args.image)
        cmd = [p.replace("{image}", args.image).replace("{family}", fam)
               for p in parts]
    else:
        cmd = [sys.executable, str(ROOT / "reader.py"), args.image, "--family", fam]
    p = subprocess.run(cmd, cwd=str(ROOT))
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
