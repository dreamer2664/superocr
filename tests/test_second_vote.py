#!/usr/bin/env python3
"""Tests for tools/second_vote.py (t-20261012-83bf): receipt, diff, alarm.

Script-style (run_all compatible): prints PASS/FAIL per check, ALL PASS at end.
Synthetic data only, seeded, offline, fast.
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "second_vote.py"
PY = sys.executable
FAILURES = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  ({extra})" if extra and not cond else ""))
    if not cond:
        FAILURES.append(name)


def make_report(sha, items_easy, items_hard, seed=1):
    """items_*: list of (id, got, match)."""
    def suite(name, items):
        return {
            "suite": name, "total": len(items),
            "correct": sum(1 for _, _, m in items if m), "pct": 0.0,
            "bar": 98, "passed": False, "excluded_count": 0, "excluded_ids": [],
            "families": {}, "median_s": 0.1, "p95_s": 0.2, "failures": [],
            "gallery": None,
            "results": [
                {"id": i, "family": i.split("-")[0], "image": f"{i}.png",
                 "label": "LBL", "got": g, "error": "", "match": m,
                 "excluded": False, "seconds": 0.05}
                for i, g, m in items
            ],
        }
    return {
        "bench": "test", "bench_version": "0", "run_id": "t1", "run_index": 0,
        "runs": 1, "started_ts": "x", "finished_ts": "y", "suite_dir": "data",
        "seed": seed, "reader": {"command": "python3 baseline.py {image}", "name": "baseline"},
        "git_commit": sha, "bars": {}, "bar_overridden": [], "excluded_count": 0,
        "galleries": {}, "totals": {},
        "suites": {"easy": suite("easy", items_easy), "hard": suite("hard", items_hard)},
        "passed": False,
    }


def run_tool(*args):
    return subprocess.run([PY, str(TOOL), *args], capture_output=True, text=True, timeout=60)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sv_test_"))
    sha_a = "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111"
    sha_b = "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222"
    items_easy = [("plain-0001", "HELLO", True), ("plain-0002", "uORLD", False)]
    items_hard = [("darts-0001", "WORLD", True)]

    # 1. receipt extraction keeps sha, reader, items; drops nothing item-level
    rep = tmp / "rep.json"
    rep.write_text(json.dumps(make_report(sha_a, items_easy, items_hard)))
    r = run_tool("receipt", str(rep), "-o", str(tmp / "rec.json"))
    check("receipt runs", r.returncode == 0, r.stderr[:120])
    rec = json.loads((tmp / "rec.json").read_text())
    check("receipt schema", rec.get("schema") == "superocr.receipt/1")
    check("receipt sha", rec["git_commit"] == sha_a)
    check("receipt items", rec["suites"]["easy"]["items"]["plain-0002"] == ["uORLD", False])
    check("receipt reader cmd", rec["reader_command"] == "python3 baseline.py {image}")

    # 2. identical diff -> exit 0, verdict ITEM-IDENTICAL (accept-trusted)
    r = run_tool("diff", str(tmp / "rec.json"), str(rep))
    check("identical diff exit 0", r.returncode == 0, str(r.returncode))
    check("identical verdict", "ITEM-IDENTICAL" in r.stdout and "accept-trusted" in r.stdout)

    # 3. one item differs -> exit 1, diff named, verdict escalate
    rep2 = tmp / "rep2.json"
    rep2.write_text(json.dumps(make_report(sha_a, [("plain-0001", "HELLO", True),
                                                    ("plain-0002", "WORLD", True)],
                                           items_hard)))
    r = run_tool("diff", str(tmp / "rec.json"), str(rep2))
    check("differing diff exit 1", r.returncode == 1, str(r.returncode))
    check("diff names the item", "plain-0002" in r.stdout)
    check("diff escalates", "ITEMS-DIFFER" in r.stdout and "full review" in r.stdout)

    # 4. sha mismatch -> exit 2, re-bind message, no item comparison pretended
    rep3 = tmp / "rep3.json"
    rep3.write_text(json.dumps(make_report(sha_b, items_easy, items_hard)))
    r = run_tool("diff", str(tmp / "rec.json"), str(rep3))
    check("sha mismatch exit 2", r.returncode == 2, str(r.returncode))
    check("sha mismatch says re-bind", "SHA-MISMATCH" in r.stdout and "bind" in r.stdout.lower())

    # 5. excluded items are not part of the receipt (they are not scored)
    rep4_data = make_report(sha_a, items_easy, items_hard)
    rep4_data["suites"]["easy"]["results"].append(
        {"id": "plain-9999", "family": "plain", "image": "x.png", "label": "L",
         "got": "", "error": "", "match": False, "excluded": True, "seconds": 0.0})
    rep4 = tmp / "rep4.json"
    rep4.write_text(json.dumps(rep4_data))
    rec4 = json.loads(subprocess.run(
        [PY, str(TOOL), "receipt", str(rep4)], capture_output=True, text=True).stdout)
    check("excluded items dropped", "plain-9999" not in rec4["suites"]["easy"]["items"])

    # 6. alarm: one task with a single 45-min-old vote alarms; fresh one stays quiet
    now = datetime.now(timezone.utc)
    old = (now - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cc = tmp / "chatcode"
    (cc / "bus").mkdir(parents=True)
    (cc / "board" / "tasks").mkdir(parents=True)
    (cc / "bus" / "general.jsonl").write_text(
        json.dumps({"id": "v1", "ts": old, "from": "marcus-aurelius", "type": "vote",
                    "ref": "t-2026-0001", "vote": "accept", "inspected": "True",
                    "reason": "x", "decisive": "False"}) + "\n" +
        json.dumps({"id": "v2", "ts": fresh, "from": "scott", "type": "vote",
                    "ref": "t-2026-0002", "vote": "accept", "inspected": "True",
                    "reason": "x", "decisive": "False"}) + "\n" +
        json.dumps({"id": "v3", "ts": old, "from": "cormac", "type": "vote",
                    "ref": "t-2026-0003", "vote": "accept", "inspected": "True",
                    "reason": "x", "decisive": "False"}) + "\n" +
        json.dumps({"id": "v4", "ts": old, "from": "scott", "type": "vote",
                    "ref": "t-2026-0003", "vote": "accept", "inspected": "True",
                    "reason": "x", "decisive": "False"}) + "\n")
    for tid, owner, status in [("t-2026-0001", "cormac", "review"),
                               ("t-2026-0002", "scott", "review"),
                               ("t-2026-0003", "barry", "review"),
                               ("t-2026-0004", "pericles", "done")]:
        (cc / "board" / "tasks" / f"{tid}.json").write_text(json.dumps(
            {"id": tid, "title": "t", "status": status, "owner": owner}))
    r = run_tool("alarm", "--chatcode", str(cc), "--min-stuck", "30")
    check("alarm exit 0", r.returncode == 0, r.stderr[:120])
    check("alarm fires on stuck task", "ALARM t-2026-0001" in r.stdout)
    check("alarm quiet on fresh task", "t-2026-0002" not in r.stdout.replace("ALARM", ""))
    check("alarm quiet on quorum-complete task", "t-2026-0003" not in r.stdout)
    check("alarm ignores done tasks", "t-2026-0004" not in r.stdout)
    # owner's own ballot must not count toward quorum (append, keep v1-v4)
    with open(cc / "bus" / "general.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": "v5", "ts": old, "from": "cormac", "type": "vote",
                            "ref": "t-2026-0001", "vote": "accept", "inspected": "True",
                            "reason": "self", "decisive": "False"}) + "\n")
    r = run_tool("alarm", "--chatcode", str(cc), "--min-stuck", "30")
    check("owner ballot not counted", "ALARM t-2026-0001" in r.stdout)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
