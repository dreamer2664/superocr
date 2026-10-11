#!/usr/bin/env python3
"""oracle_reader.py — TEST FIXTURE ONLY: always correct, by reading the manifest.

Not a reader: it exists so tests can prove the S5 harness CAN go green (a proof
tool that cannot pass anything would be worthless). Never use it for a score.
"""
import json
import sys
from pathlib import Path

img = Path(sys.argv[1]).resolve()
suite = img.parent.parent
for line in (suite / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    row = json.loads(line)
    rel = row.get("image") or row.get("file")
    if (suite / rel).resolve() == img:
        print(row["label"])
        sys.exit(0)
sys.exit(1)
