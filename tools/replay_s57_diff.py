#!/usr/bin/env python3
"""S57 replay diff — compare replay bench receipts against committed receipts.

Per the S57 contract (t-20261014-713e): diff per-item (id, got) of each
replay run against the matching committed run of the 3x receipt set, for
both suites. Counts must be compared, not eyeballed: this tool emits a
machine-readable summary and exits non-zero on ANY variance, so a
non-identical replay can never pass silently.

Usage:
    python3 tools/replay_s57_diff.py --replay reports/replay-s55/<date>/seed1-3x \
        --committed reports/s55-bench-seed1-3x --seed 1 [--out summary.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

RUN_RE = re.compile(r"-easy-hard-r(\d+)of\d+\.json$")


def _runs(report_dir: Path) -> dict[int, Path]:
    """Map run index -> receipt path for <ts>-easy-hard-r{i}of{n}.json files."""
    out: dict[int, Path] = {}
    for p in sorted(report_dir.glob("*-easy-hard-r*of*.json")):
        m = RUN_RE.search(p.name)
        if m:
            out[int(m.group(1))] = p
    return out


def _rows_by_id(report: dict, suite: str) -> dict[str, str]:
    return {r["id"]: r["got"] for r in report["suites"][suite]["results"]}


def diff_pair(replay: dict, committed: dict) -> dict:
    """Per-suite per-item (id, got) diff between two receipts."""
    out: dict[str, dict] = {}
    for suite in ("easy", "hard"):
        a = _rows_by_id(replay, suite)
        b = _rows_by_id(committed, suite)
        only_replay = sorted(set(a) - set(b))
        only_committed = sorted(set(b) - set(a))
        diffs = sorted(i for i in set(a) & set(b) if a[i] != b[i])
        out[suite] = {
            "items_compared": len(set(a) & set(b)),
            "got_mismatches": len(diffs),
            "mismatch_ids": diffs,
            "id_only_in_replay": only_replay,
            "id_only_in_committed": only_committed,
            "replay_correct": replay["suites"][suite]["correct"],
            "committed_correct": committed["suites"][suite]["correct"],
            "counts_identical": (
                replay["suites"][suite]["correct"] == committed["suites"][suite]["correct"]
            ),
            "identical": not (diffs or only_replay or only_committed)
            and counts_eq(replay, committed, suite),
        }
    return out


def counts_eq(replay: dict, committed: dict, suite: str) -> bool:
    return replay["suites"][suite]["correct"] == committed["suites"][suite]["correct"]


def diff_dirs(replay_dir: Path, committed_dir: Path, seed: int) -> dict:
    r_runs = _runs(replay_dir)
    c_runs = _runs(committed_dir)
    if not r_runs or not c_runs:
        raise SystemExit(f"no run receipts found in {replay_dir} or {committed_dir}")
    if set(r_runs) != set(c_runs):
        raise SystemExit(
            f"run-index mismatch: replay {sorted(r_runs)} vs committed {sorted(c_runs)}"
        )
    per_run: dict[str, dict] = {}
    all_identical = True
    for i in sorted(r_runs):
        replay = json.loads(r_runs[i].read_text())
        committed = json.loads(c_runs[i].read_text())
        if replay.get("seed") != seed or committed.get("seed") != seed:
            raise SystemExit(f"run {i}: seed stamp is not {seed}")
        pair = diff_pair(replay, committed)
        run_identical = all(s["identical"] for s in pair.values())
        all_identical = all_identical and run_identical
        per_run[f"r{i}"] = {
            "replay_receipt": r_runs[i].name,
            "committed_receipt": c_runs[i].name,
            "suites": pair,
            "identical": run_identical,
        }
    return {
        "seed": seed,
        "runs_compared": len(per_run),
        "all_runs_identical": all_identical,
        "runs": per_run,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--replay", required=True, help="replay receipt dir")
    ap.add_argument("--committed", required=True, help="committed 3x receipt dir")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", help="write JSON summary here")
    args = ap.parse_args(argv)

    summary = diff_dirs(Path(args.replay), Path(args.committed), args.seed)
    text = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    if not summary["all_runs_identical"]:
        print("VARIANCE DETECTED — replay is NOT identical; report and stop.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
