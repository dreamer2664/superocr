#!/usr/bin/env python3
"""Mechanical second vote + quorum starvation alarm (t-20261012-83bf).

Room decision t-ef72 (2026-10-12): reviewer receipts carry item-level JSON at
the head sha they covered; a second voter runs ONE 1-run screen, diffs it
against the first reviewer's receipt, and

  * item-identical at the SAME head sha  -> an honest accept-trusted (R12),
  * ANY item diff                        -> escalate to a full review,
  * sha mismatch                         -> re-bind the review to a sha first.

and any task sitting one vote from quorum for >30 minutes raises an alarm.

Subcommands
-----------
receipt <bench-report.json> [-o OUT]
    Extract a stampable receipt from a bench report: head sha, reader command,
    seed, and per-suite item-level results {id: [got, match]}. A receipt is
    what the first reviewer ships with their vote.

diff <first-receipt.json> <second-report-or-receipt.json>
    Item-level comparison of two receipts (a bench report is accepted directly
    and converted). Exit codes:
        0  ITEM-IDENTICAL   -> accept-trusted is honest
        1  ITEMS-DIFFER     -> escalate to full review (diffs listed)
        2  SHA-MISMATCH     -> receipts cover different heads; re-bind first
        3  usage/schema error

alarm --chatcode <repo-path> [--min-stuck MINUTES]
    Tally votes per task from the chatcode bus (bus/*.jsonl) and report every
    task whose tally is exactly one non-owner vote and whose first vote is
    older than --min-stuck (default 30). These are the quorum-starvation
    candidates the silence-style watch should alert the free agents about.

Everything here is stdlib-only and read-only: no repo is written.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "superocr.receipt/1"


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        sys.exit(3)


def receipt_from_report(report: dict) -> dict:
    """Reduce a bench report to the stampable receipt fields."""
    if "suites" not in report or "git_commit" not in report:
        raise ValueError("not a bench report (missing 'suites' / 'git_commit')")
    suites = {}
    for name, s in report["suites"].items():
        items = {}
        for r in s.get("results", []):
            if r.get("excluded"):
                continue
            items[r["id"]] = [r.get("got", ""), bool(r.get("match"))]
        suites[name] = {"total": s.get("total"), "correct": s.get("correct"),
                        "items": items}
    reader = report.get("reader") or {}
    return {
        "schema": SCHEMA,
        "git_commit": report["git_commit"],
        "reader_command": reader.get("command", ""),
        "seed": report.get("seed"),
        "run_id": report.get("run_id", ""),
        "suites": suites,
    }


def as_receipt(obj: dict) -> dict:
    """Accept either a receipt or a full bench report."""
    if obj.get("schema") == SCHEMA:
        return obj
    return receipt_from_report(obj)


def diff_receipts(first: dict, second: dict) -> tuple[int, list[str]]:
    """Compare two receipts item-level. Returns (exit_code, lines)."""
    if first["git_commit"] != second["git_commit"]:
        return 2, [f"sha-mismatch: first covers {first['git_commit'][:10]}, "
                   f"second covers {second['git_commit'][:10]}"]
    lines: list[str] = []
    code = 0
    names = sorted(set(first["suites"]) | set(second["suites"]))
    for name in names:
        a = first["suites"].get(name, {}).get("items", {})
        b = second["suites"].get(name, {}).get("items", {})
        ids = sorted(set(a) | set(b))
        diffs = []
        for i in ids:
            va, vb = a.get(i), b.get(i)
            if va != vb:
                diffs.append(f"  {name}/{i}: first={va} second={vb}")
        if diffs:
            code = 1
            lines.append(f"{name}: {len(diffs)} item diff(s) of {len(ids)}")
            lines.extend(diffs[:50])
            if len(diffs) > 50:
                lines.append(f"  ... and {len(diffs) - 50} more")
        else:
            lines.append(f"{name}: {len(ids)} items identical")
    return code, lines


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def alarm(chatcode_repo: Path, min_stuck: int) -> int:
    """List tasks one vote from quorum for longer than min_stuck minutes."""
    bus = chatcode_repo / "bus"
    votes: dict[str, list[dict]] = {}
    for f in sorted(bus.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("type") != "vote" or not m.get("ref"):
                continue
            votes.setdefault(m["ref"], []).append(m)

    tasks_dir = chatcode_repo / "board" / "tasks"
    owners: dict[str, str] = {}
    open_refs: set[str] = set()
    for f in tasks_dir.glob("*.json"):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        owners[t["id"]] = t.get("owner") or ""
        if t.get("status") in ("claimed", "review"):
            open_refs.add(t["id"])

    now = datetime.now(timezone.utc)
    stuck, done = [], 0
    for ref in sorted(open_refs):
        vs = votes.get(ref, [])
        # non-owner ballots only; quorum is two.
        ballots = [v for v in vs if v.get("from") != owners.get(ref)]
        if len(ballots) != 1:
            continue
        ts = _parse_ts(ballots[0].get("ts", ""))
        if ts is None:
            continue
        age_min = (now - ts).total_seconds() / 60.0
        if age_min >= min_stuck:
            stuck.append(f"ALARM {ref}: 1 vote ({ballots[0].get('vote')}) "
                         f"from {ballots[0].get('from')}, stuck {age_min:.0f} min "
                         f"(>={min_stuck}) — needs one free agent")
        else:
            done += 1
    for line in stuck:
        print(line)
    if not stuck:
        print(f"no task stuck one-vote-from-quorum for >={min_stuck} min"
              f" ({done} one-vote task(s) still inside the window)")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("receipt", help="extract a receipt from a bench report")
    p_rec.add_argument("report", help="bench report JSON")
    p_rec.add_argument("-o", "--out", help="write the receipt here (default stdout)")

    p_diff = sub.add_parser("diff", help="item-level diff of two receipts")
    p_diff.add_argument("first", help="first reviewer's receipt (or bench report)")
    p_diff.add_argument("second", help="second reviewer's receipt/bench report")

    p_alarm = sub.add_parser("alarm", help="quorum-starvation watch")
    p_alarm.add_argument("--chatcode", required=True,
                         help="path to a chatcode checkout (bus/ + board/tasks/)")
    p_alarm.add_argument("--min-stuck", type=int, default=30,
                         help="minutes one-vote-from-quorum before alarm (30)")

    args = ap.parse_args()

    if args.cmd == "receipt":
        rec = receipt_from_report(_load_json(args.report))
        text = json.dumps(rec, indent=1, sort_keys=True)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
            print(f"receipt written to {args.out} (sha {rec['git_commit'][:10]}, "
                  f"{sum(len(s['items']) for s in rec['suites'].values())} items)")
        else:
            print(text)
        return

    if args.cmd == "diff":
        try:
            first = as_receipt(_load_json(args.first))
            second = as_receipt(_load_json(args.second))
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(3)
        code, lines = diff_receipts(first, second)
        verdict = {0: "ITEM-IDENTICAL: accept-trusted is honest (R12)",
                   1: "ITEMS-DIFFER: escalate to a full review",
                   2: "SHA-MISMATCH: bind the review to a sha first"}[code]
        print(f"head sha: {first['git_commit'][:10]}")
        for line in lines:
            print(line)
        print(verdict)
        sys.exit(code)

    if args.cmd == "alarm":
        sys.exit(alarm(Path(args.chatcode), args.min_stuck))


if __name__ == "__main__":
    main()
