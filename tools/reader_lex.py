#!/usr/bin/env python3
"""Bench reader wrapper: classic floor + lex-projection post-pass.

Usage (as a bench reader command):
    python3 tools/reader_lex.py {image}

Runs the repo's own reader (baseline.py) on the image and applies the
reader-agnostic lex-projection post-pass (tools/lex_projection.py) to the
decoded text. Deterministic, no external services, no network.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lex_projection import fix_line  # noqa: E402

img = sys.argv[1]
out = subprocess.run([sys.executable, str(HERE.parent / "baseline.py"), img],
                     capture_output=True, text=True)
if out.returncode != 0:
    sys.stderr.write(out.stderr)
    sys.exit(out.returncode)
print(fix_line(out.stdout.strip()))
