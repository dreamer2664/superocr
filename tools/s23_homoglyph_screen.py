#!/usr/bin/env python3
"""Offline ablation of the S23 0/1 homoglyph rule on saved OCR row JSON.

This does not run a reader or write to the input files. It compares the plain
rows and ``lex_projection.fix_line`` output against the same stored labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import homoglyph_fix  # noqa: E402
from tools.lex_projection import fix_line  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def evaluate(rows, route: str, policy: str) -> dict:
    result = {}
    for suite in ("easy", "hard"):
        subset = [r for r in rows if r["suite"] == suite]
        before = after = rescued = regressed = wrong_changed = text_changed = 0
        details = []
        for row in subset:
            raw = row["got"]
            baseline = fix_line(raw) if route == "lex" else raw
            candidate = homoglyph_fix.fix_text(raw, policy)
            if route == "lex":
                candidate = fix_line(candidate)
            label = row["label"]
            bmatch = baseline == label
            cmatch = candidate == label
            before += bmatch
            after += cmatch
            if baseline != candidate:
                text_changed += 1
                if not bmatch and cmatch:
                    rescued += 1
                    kind = "fix"
                elif bmatch and not cmatch:
                    regressed += 1
                    kind = "break"
                else:
                    wrong_changed += 1
                    kind = "wrong-to-wrong"
                details.append({
                    "id": row["id"], "kind": kind, "label": label,
                    "baseline": baseline, "candidate": candidate,
                })
        result[suite] = {
            "n": len(subset), "before": before, "after": after,
            "delta": after - before, "rescued": rescued,
            "regressed": regressed, "wrong_to_wrong": wrong_changed,
            "text_changed": text_changed, "details": details,
        }
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rows", nargs="+", type=Path,
                    help="saved check_rows.py JSON output files")
    ap.add_argument("--policies", nargs="+", choices=("r4", "upper"),
                    default=("r4", "upper"))
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="emit the complete machine-readable result")
    args = ap.parse_args(argv)

    report = {
        "screen": "S23 stored-row transform ablation; no reader run",
        "scorer": "exact output string == row['label']",
        "files": [],
    }
    for path in args.rows:
        rows = json.loads(path.read_text(encoding="utf-8"))
        required = {"id", "suite", "label", "got"}
        if not isinstance(rows, list) or any(not required <= set(r) for r in rows):
            ap.error(f"{path}: expected a JSON list with fields {sorted(required)}")
        mixed_label_tokens = sum(
            1 for row in rows for token in row["label"].split()
            if any(c in "01" for c in token) and any(c.isalpha() for c in token)
        )
        file_result = {
            "path": str(path), "sha256": sha256(path), "rows": len(rows),
            "mixed_01_alphanumeric_label_tokens": mixed_label_tokens,
            "policies": {},
        }
        for policy in args.policies:
            file_result["policies"][policy] = {
                route: evaluate(rows, route, policy) for route in ("plain", "lex")
            }
        report["files"].append(file_result)

    if args.as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print(report["screen"])
    print(report["scorer"])
    for file_result in report["files"]:
        print(f"\n{file_result['path']}  sha256={file_result['sha256']}  N={file_result['rows']}")
        for policy, routes in file_result["policies"].items():
            for route, suites in routes.items():
                for suite, stats in suites.items():
                    print(
                        f"  {policy:5} {route:5} {suite:4} "
                        f"{stats['before']:3}->{stats['after']:3} "
                        f"delta={stats['delta']:+d} "
                        f"fix={stats['rescued']} break={stats['regressed']} "
                        f"wrong-to-wrong={stats['wrong_to_wrong']} "
                        f"text-change={stats['text_changed']}"
                    )
                for suite, stats in suites.items():
                    for detail in stats["details"]:
                        print(
                            f"    {suite} {detail['kind']:13} {detail['id']}: "
                            f"{detail['baseline']!r} -> {detail['candidate']!r} "
                            f"(label {detail['label']!r})"
                        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
