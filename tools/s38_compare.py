#!/usr/bin/env python3
"""S38: audit and compare canonical seed-1/seed-2 bench receipts.

No OCR is run here. The committed seed-1 receipt is a historical comparator,
not a fresh run; the report must establish shipping-source identity separately.
Usage: python3 tools/s38_compare.py SEED1.json SEED2.json --out summary.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from math import comb, sqrt
from pathlib import Path

HASHES = {
    1: "b2c460d2fb5a8f83c8d4c4b3893ff6eb05248f2444cbb1ff8acbe9531323fdd3",
    2: "ec64cd63790d8824b4f72c71d18dd953326c24da01d65d171938ae79beb549e8",
}
COMMAND = "python3 tools/reader_lex.py {image}"


def audit(report: dict, seed: int) -> None:
    """Refuse incomplete, noncanonical, overridden, or internally wrong counts."""
    if report.get("seed") != seed:
        raise ValueError("wrong seed")
    stamps = report.get("stamps", {})
    if stamps.get("dir_hash") != HASHES[seed]:
        raise ValueError("noncanonical suite hash")
    if stamps.get("reader_command") != COMMAND or report.get("reader", {}).get("command") != COMMAND:
        raise ValueError("wrong reader command")
    if stamps.get("scorer") not in ("author", "iris", "both"):
        raise ValueError("invalid scorer")
    if any(not isinstance(stamps.get("env", {}).get(k), str) or not stamps["env"][k]
           for k in ("python", "pillow", "numpy", "cv2")):
        raise ValueError("missing environment stamp")
    if report.get("bar_overridden") or report.get("bars") != {"easy": 98, "hard": 95}:
        raise ValueError("overridden bars")
    if not report.get("coop", {}).get("finished"):
        raise ValueError("unfinished receipt")
    if set(report.get("suites", {})) != {"easy", "hard"}:
        raise ValueError("both suites required")
    for name, suite in report["suites"].items():
        rows = suite.get("results", [])
        if suite.get("total") != 100 or len(rows) != 100:
            raise ValueError("each suite requires all 100 results")
        if len({r["id"] for r in rows}) != 100:
            raise ValueError("duplicate result IDs")
        if suite.get("excluded_count") or any(r.get("excluded") for r in rows):
            raise ValueError("excluded item")
        if any(r.get("error") is not None for r in rows):
            raise ValueError("reader error or timeout; investigate before comparing")
        for row in rows:
            if not isinstance(row.get("label"), str) or not isinstance(row.get("got"), str):
                raise ValueError("missing text")
            if row.get("match") is not (row["got"] == row["label"]):
                raise ValueError("incorrect exact-match flag")
        if suite.get("correct") != sum(r["match"] for r in rows):
            raise ValueError("incorrect suite count")
        if suite.get("passed") != (suite["correct"] >= report["bars"][name]):
            raise ValueError("incorrect bar verdict")
        families = suite.get("families", {})
        if set(families) != {r["family"] for r in rows}:
            raise ValueError("family set mismatch")
        for family, counts in families.items():
            selected = [r for r in rows if r["family"] == family]
            if counts["total"] != len(selected) or counts["correct"] != sum(r["match"] for r in selected):
                raise ValueError("incorrect family count")


def wilson(correct: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = correct / total
    denom = 1 + z * z / total
    mid = (p + z * z / (2 * total)) / denom
    half = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [round(100 * (mid - half), 3), round(100 * (mid + half), 3)]


def fisher_two_sided(c1: int, n1: int, c2: int, n2: int) -> float:
    """Independent seeds: Fisher exact, not a paired test on repeated IDs."""
    successes, total = c1 + c2, n1 + n2
    lo, hi = max(0, n1 - (total - successes)), min(n1, successes)
    def weight(k):
        return comb(successes, k) * comb(total - successes, n1 - k)
    observed = weight(c1)
    return sum(weight(k) for k in range(lo, hi + 1) if weight(k) <= observed) / comb(total, n1)


def signature(row: dict) -> str:
    """Observable string signatures ONLY, not segmentation/matching diagnoses."""
    got, label = row["got"], row["label"]
    if got == label:
        return "exact"
    if got.lower() == label.lower():
        return "case-only"
    if len(got) < len(label):
        return "shorter-output"
    if len(got) > len(label):
        return "longer-output"
    return "same-length-substitution"


def compare(first: dict, second: dict) -> dict:
    audit(first, 1)
    audit(second, 2)
    if first["stamps"]["env"] != second["stamps"]["env"]:
        raise ValueError("environment mismatch")
    out = {"reader_command": COMMAND, "env": second["stamps"]["env"],
           "seed1_commit": first["git_commit"], "seed2_commit": second["git_commit"],
           "suites": {}, "interpretation": "One fresh seed-2 screen versus a historical same-route seed-1 receipt; not three-run stability proof. IDs reused across seeds identify different images, so inference is unpaired. String signatures are not root-cause diagnoses."}
    for name in ("easy", "hard"):
        a, b = first["suites"][name], second["suites"][name]
        if {f: v["total"] for f, v in a["families"].items()} != {f: v["total"] for f, v in b["families"].items()}:
            raise ValueError("family composition mismatch")
        c1, c2 = a["correct"], b["correct"]
        delta = c2 - c1  # each arm has exactly 100 items
        out["suites"][name] = {
            "seed1_correct": c1, "seed2_correct": c2, "per_seed_total": 100,
            "delta_percentage_points": delta, "pooled_correct": c1 + c2,
            "pooled_total": 200, "pooled_percent": (c1 + c2) / 2,
            "seed1_wilson_95_percent": wilson(c1, 100),
            "seed2_wilson_95_percent": wilson(c2, 100),
            "fisher_two_sided_p": round(fisher_two_sided(c1, 100, c2, 100), 6),
            "task_gap_trigger": "investigate (>5pp)" if abs(delta) > 5 else "within +/-2pp" if abs(delta) <= 2 else "intermediate (3-5pp)",
            "families": {f: {"total_per_seed": a["families"][f]["total"],
                             "seed1_correct": a["families"][f]["correct"],
                             "seed2_correct": b["families"][f]["correct"],
                             "count_delta": b["families"][f]["correct"] - a["families"][f]["correct"]}
                         for f in a["families"]},
            "seed1_signatures": dict(Counter(signature(r) for r in a["results"])),
            "seed2_signatures": dict(Counter(signature(r) for r in b["results"])),
            "seed2_errors": 0, "seed2_excluded": 0,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("seed1", type=Path)
    ap.add_argument("seed2", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    try:
        result = compare(json.loads(args.seed1.read_text()), json.loads(args.seed2.read_text()))
    except (ValueError, KeyError, TypeError, OSError) as e:
        ap.exit(1, f"REFUSED: {e}\n")
    result["seed1_receipt"] = str(args.seed1)
    result["seed2_receipt"] = str(args.seed2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["suites"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
