#!/usr/bin/env python3
"""Reproducibility-gate validator — the reviewer side of the four stamps
(room decision t-20261012-ef72, task t-20261012-eb76).

Bench (scott's side, t-20261012-5e8a) refuses to write a report without:

    "stamps": {
        "dir_hash":       "<sha256 hex of the suite data root>",   # tools/make_suites.py dir_hash
        "reader_command": "<the exact command string that was run>",
        "env":            {"python": "...", "pillow": "...",
                           "numpy": "...", "cv2": "..."},           # "absent" is a legal value
        "scorer":         "author" | "iris" | "both"
    }

This tool checks a report WITHOUT re-running anything: presence, format,
cross-consistency, and — optionally — re-hashes the data dir so a quoted
hash can never stand in for the real bytes (the S14 failure mode:
t-20261012-1d17, claimed 0.707 vs 0.302 on hash-identical images).

Verdicts and exit codes:
    PASS        0   all stamps present and valid (verified where asked)
    FAIL        1   missing/malformed/mismatched stamp — reject at review
    UNSTAMPED   2   legacy report written before the gate — not a crash

Examples:
    tools/validate_report.py reports/run.json
    tools/validate_report.py reports/run.json --data data --expect-scorer author
    tools/validate_report.py reports/run.json --data data --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_suites import dir_hash  # noqa: E402  (single source of truth)

SCORERS = ("author", "iris", "both")
ENV_KEYS = ("python", "pillow", "numpy", "cv2")
ABSENT = "absent"
HEX64 = set("0123456789abcdef")


def _fail(reasons: list[str]) -> dict:
    return {"verdict": "FAIL", "reasons": reasons}


def check_stamps(report: dict, expect_scorer: str | None = None,
                 expect_cmd: str | None = None) -> tuple[dict, list[str]]:
    """Validate the stamps block in isolation. Returns (stamps, reasons)."""
    reasons: list[str] = []
    stamps = report.get("stamps")
    if not isinstance(stamps, dict):
        return {}, ["no 'stamps' object in report (legacy: written before the gate)"]

    dh = stamps.get("dir_hash")
    if not isinstance(dh, str) or len(dh) != 64 or not set(dh.lower()) <= HEX64:
        reasons.append(f"dir_hash: expected 64-hex sha256, got {dh!r}")
    cmd = stamps.get("reader_command")
    if not isinstance(cmd, str) or not cmd.strip():
        reasons.append(f"reader_command: expected non-empty string, got {cmd!r}")
    elif expect_cmd and cmd != expect_cmd:
        reasons.append(f"reader_command: {cmd!r} != expected {expect_cmd!r}")

    # cross-check: the stamp must agree with the reader block bench already writes
    bench_cmd = (report.get("reader") or {}).get("command")
    if isinstance(bench_cmd, str) and isinstance(cmd, str) and bench_cmd != cmd:
        reasons.append(f"reader_command {cmd!r} disagrees with reader.command {bench_cmd!r}")

    env = stamps.get("env")
    if not isinstance(env, dict):
        reasons.append("env: expected an object of component->version")
    else:
        for key in ENV_KEYS:
            val = env.get(key)
            if not isinstance(val, str) or not val.strip():
                reasons.append(f"env.{key}: missing or not a string (use 'absent' if not installed)")
    if "suite_dir" in report and isinstance(env, dict):
        reasons.append("hint: report carries an absolute suite_dir; the gate's dir_hash "
                       "replaces path identity with content identity — do not compare paths")

    scorer = stamps.get("scorer")
    if scorer not in SCORERS:
        reasons.append(f"scorer: expected one of {SCORERS}, got {scorer!r}")
    elif expect_scorer and scorer != expect_scorer:
        reasons.append(f"scorer: {scorer!r} != expected {expect_scorer!r}")

    return stamps, reasons


def current_env() -> dict:
    """The env fingerprint of the machine running the validator (for --compare-env)."""
    env = {"python": platform.python_version()}
    for key, mod in (("pillow", "PIL"), ("numpy", "numpy"), ("cv2", "cv2")):
        try:
            env[key] = __import__(mod).__version__
        except Exception:                                  # noqa: BLE001
            env[key] = ABSENT
    return env


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("report", help="path to a bench report .json")
    ap.add_argument("--data", metavar="DIR",
                    help="re-hash this suite root and compare to the stamp "
                         "(the quoting-is-not-re-hashing check)")
    ap.add_argument("--expect-scorer", choices=SCORERS,
                    help="fail unless the scorer identity is this")
    ap.add_argument("--expect-cmd", metavar="CMD",
                    help="fail unless the reader command equals this")
    ap.add_argument("--compare-env", action="store_true",
                    help="report this box's env next to the stamp (mismatch is "
                         "information, not failure — the stamp describes the "
                         "author's box; with --strict-env it fails)")
    ap.add_argument("--strict-env", action="store_true",
                    help="with --compare-env: an env mismatch is a FAIL")
    ap.add_argument("--strict", action="store_true",
                    help="UNSTAMPED counts as FAIL (for post-gate reports)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    out: dict = {"report": args.report}
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        out.update(_fail([f"cannot read report: {e}"]))
        print(json.dumps(out) if args.json else f"FAIL {out['reasons'][0]}")
        return 1

    stamps, reasons = check_stamps(report, args.expect_scorer, args.expect_cmd)

    if not stamps:                                        # legacy / unstamped
        verdict = "FAIL" if args.strict else "UNSTAMPED"
        out.update({"verdict": verdict, "reasons": reasons})
        if args.json:
            print(json.dumps(out))
        else:
            print(f"{verdict}: {reasons[0]}")
            print("  pre-gate report — ask the author to regenerate on a stamped bench, "
                  "or hand-verify per BENCH.md 'Reproducibility stamps'")
        return 1 if args.strict else 2

    if args.data:
        actual = dir_hash(Path(args.data))
        out["dir_hash_recomputed"] = actual
        if actual != stamps.get("dir_hash"):
            reasons.append(f"dir_hash: stamp {stamps.get('dir_hash', '')[:16]}… "
                           f"but re-hash of {args.data} is {actual[:16]}… — "
                           "the report does not describe these bytes")

    if args.compare_env:
        here = current_env()
        out["env_here"] = here
        stamped = stamps.get("env") or {}
        diff = {k: (stamped.get(k), here.get(k)) for k in ENV_KEYS
                if stamped.get(k) != here.get(k)}
        if diff:
            out["env_diff"] = diff
            msg = ("env: this box differs from the stamp on " + ", ".join(sorted(diff)))
            if args.strict_env:
                reasons.append(msg + " (--strict-env)")
            else:
                out.setdefault("notes", []).append(msg)

    if reasons:
        out.update(_fail(reasons))
    else:
        out["verdict"] = "PASS"
        out["stamps"] = stamps
        out.setdefault("notes", [])
        if not args.data:
            out["notes"].append("dir_hash validated for format only — "
                                "pass --data <suite root> to re-hash the bytes")

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(out["verdict"])
        for r in reasons:
            print(f"  ✗ {r}")
        for n in out.get("notes", []):
            print(f"  · {n}")
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
