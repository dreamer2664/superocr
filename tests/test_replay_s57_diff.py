#!/usr/bin/env python3
"""Tests for tools/replay_s57_diff.py — the S57 replay comparator.

The comparator is the receipt for the replay; if it is wrong, the replay
proves nothing. These cases pin its behaviour: identical receipts pass,
any (id, got) variance fails, id-set variance fails, count-only variance
fails, and order does not matter.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import replay_s57_diff as rd  # noqa: E402


def make_receipt(seed: int, run: int) -> dict:
    rows = {"easy": [(f"easy-{i:04d}", f"word {i}") for i in range(3)],
            "hard": [(f"hard-{i:04d}", f"tough {i}") for i in range(2)]}
    suites = {}
    for name, rr in rows.items():
        suites[name] = {
            "suite": name,
            "total": len(rr),
            "correct": sum(1 for _, g in rr if "0" in g or "1" in g),
            "results": [{"id": i, "got": g, "label": g, "match": True} for i, g in rr],
        }
    return {"seed": seed, "run_index": run, "suites": suites}


def write_run(d: Path, receipt: dict, tag: str) -> None:
    (d / f"20260101T000000Z-{tag}-easy-hard-r{receipt['run_index']}of3.json").write_text(
        json.dumps(receipt)
    )


def case_identical_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        r_dir, c_dir = Path(td) / "r", Path(td) / "c"
        r_dir.mkdir(); c_dir.mkdir()
        for i in (1, 2, 3):
            write_run(r_dir, make_receipt(1, i), "replay")
            write_run(c_dir, make_receipt(1, i), "committed")
        s = rd.diff_dirs(r_dir, c_dir, 1)
        assert s["all_runs_identical"] and s["runs_compared"] == 3
        with contextlib.redirect_stdout(io.StringIO()):
            assert rd.main(["--replay", str(r_dir), "--committed", str(c_dir), "--seed", "1"]) == 0


def case_got_variance_fails() -> None:
    with tempfile.TemporaryDirectory() as td:
        r_dir, c_dir = Path(td) / "r", Path(td) / "c"
        r_dir.mkdir(); c_dir.mkdir()
        base = make_receipt(1, 1)
        mutated = copy.deepcopy(base)
        mutated["suites"]["easy"]["results"][1]["got"] = "word DIFFERENT"
        write_run(r_dir, mutated, "replay")
        write_run(c_dir, base, "committed")
        s = rd.diff_dirs(r_dir, c_dir, 1)
        assert not s["all_runs_identical"]
        suite = s["runs"]["r1"]["suites"]["easy"]
        assert suite["got_mismatches"] == 1 and suite["mismatch_ids"] == ["easy-0001"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            assert rd.main(["--replay", str(r_dir), "--committed", str(c_dir), "--seed", "1"]) == 1


def case_count_only_variance_fails() -> None:
    # same per-item rows, different correct count => internally inconsistent
    # receipts; the comparator must not call that identical.
    with tempfile.TemporaryDirectory() as td:
        r_dir, c_dir = Path(td) / "r", Path(td) / "c"
        r_dir.mkdir(); c_dir.mkdir()
        base = make_receipt(1, 1)
        shifted = copy.deepcopy(base)
        shifted["suites"]["hard"]["correct"] += 1
        write_run(r_dir, base, "replay")
        write_run(c_dir, shifted, "committed")
        s = rd.diff_dirs(r_dir, c_dir, 1)
        assert not s["runs"]["r1"]["suites"]["hard"]["identical"]
        assert not s["all_runs_identical"]


def case_id_set_variance_fails() -> None:
    with tempfile.TemporaryDirectory() as td:
        r_dir, c_dir = Path(td) / "r", Path(td) / "c"
        r_dir.mkdir(); c_dir.mkdir()
        base = make_receipt(1, 1)
        extra = copy.deepcopy(base)
        extra["suites"]["easy"]["results"].append(
            {"id": "easy-9999", "got": "x", "label": "x", "match": True}
        )
        write_run(r_dir, extra, "replay")
        write_run(c_dir, base, "committed")
        s = rd.diff_dirs(r_dir, c_dir, 1)
        assert s["runs"]["r1"]["suites"]["easy"]["id_only_in_replay"] == ["easy-9999"]
        assert not s["all_runs_identical"]


def case_order_independent() -> None:
    with tempfile.TemporaryDirectory() as td:
        r_dir, c_dir = Path(td) / "r", Path(td) / "c"
        r_dir.mkdir(); c_dir.mkdir()
        base = make_receipt(1, 1)
        shuffled = copy.deepcopy(base)
        shuffled["suites"]["easy"]["results"].reverse()
        write_run(r_dir, shuffled, "replay")
        write_run(c_dir, base, "committed")
        s = rd.diff_dirs(r_dir, c_dir, 1)
        assert s["all_runs_identical"]


def case_seed_mismatch_refused() -> None:
    with tempfile.TemporaryDirectory() as td:
        r_dir, c_dir = Path(td) / "r", Path(td) / "c"
        r_dir.mkdir(); c_dir.mkdir()
        write_run(r_dir, make_receipt(2, 1), "replay")
        write_run(c_dir, make_receipt(2, 1), "committed")
        try:
            rd.diff_dirs(r_dir, c_dir, 1)
        except SystemExit as e:
            assert "seed stamp" in str(e)
            return
        raise AssertionError("seed mismatch must be refused")


CASES = [
    ("identical receipts pass", case_identical_passes),
    ("got variance fails with id listed", case_got_variance_fails),
    ("count-only variance fails", case_count_only_variance_fails),
    ("id-set variance fails", case_id_set_variance_fails),
    ("row order does not matter", case_order_independent),
    ("wrong seed refused", case_seed_mismatch_refused),
]

if __name__ == "__main__":
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok  {name}")
        except AssertionError as e:
            fails += 1
            print(f"FAIL  {name}: {e}")
    print(f"{len(CASES) - fails}/{len(CASES)} checks passed")
    raise SystemExit(1 if fails else 0)
