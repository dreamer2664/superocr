#!/usr/bin/env python3
"""t-20261011-b0cb (S5): the truth-run tools — suite builder + proof memo.

What is pinned here:
  * suites are deterministic and bench.py --validate accepts them;
  * a reader that is always right makes the proof say CLEARED and exit 0;
  * a reader that is always wrong makes the proof say NOT CLEARED, name the run
    and suite and the gap, keep the failure gallery, and exit 1 — a proof tool
    that cannot fail is not a proof tool;
  * the adapter derives the family from the file stem bench.py hands it.

Run: python3 tests/test_three_run_proof.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def run(*args, timeout=900):
    return subprocess.run([PY, *args], cwd=str(ROOT), text=True,
                          capture_output=True, timeout=timeout)


@check("make_suites: deterministic, valid per bench.py")
def _determinism():
    with tempfile.TemporaryDirectory() as td:
        a = run("tools/make_suites.py", "--easy", "6", "--hard", "6", "--seed", "2",
                "--out", f"{td}/data")
        assert a.returncode == 0, a.stderr
        chk = run("tools/make_suites.py", "--easy", "6", "--hard", "6", "--seed", "2",
                  "--check")
        assert chk.returncode == 0, chk.stdout + chk.stderr
        rows = [json.loads(l) for l in
                open(f"{td}/data/hard/manifest.jsonl", encoding="utf-8")]
        assert len(rows) == 6 and len({r["id"] for r in rows}) == 6
        assert len({r["family"] for r in rows}) == 6, "hard suite must spread the families"
        assert all((Path(td) / "data" / "hard" / r["image"]).exists() for r in rows)


@check("oracle reader -> proof CLEARED, exit 0, three run files")
def _oracle():
    with tempfile.TemporaryDirectory() as td:
        p = run("tools/three_run_proof.py", "--reader",
                f"{PY} tests/fixtures/oracle_reader.py {{image}}", "--runs", "3",
                "--easy", "6", "--hard", "6", "--suite-dir", f"{td}/data",
                "--out", f"{td}/proof.md", "--report-dir", f"{td}/runs")
        assert p.returncode == 0, (p.returncode, p.stdout[-600:], p.stderr[-600:])
        memo = Path(f"{td}/proof.md").read_text(encoding="utf-8")
        assert "CLEARED" in memo and "NOT CLEARED" not in memo
        assert "| 1 |" in memo and "| 2 |" in memo and "| 3 |" in memo
        js = [p for p in Path(f"{td}/runs").glob("*.json") if "stability" not in p.name]
        assert len(js) == 3, [str(x) for x in Path(f"{td}/runs").glob("*.json")]
        assert list(Path(f"{td}/runs").glob("*stability*.json")), "bench stability file"


@check("mute reader -> proof NOT CLEARED, names run+suite, gallery kept, exit 1")
def _mute():
    with tempfile.TemporaryDirectory() as td:
        p = run("tools/three_run_proof.py", "--reader",
                f"{PY} tests/fixtures/mute_reader.py {{image}}", "--runs", "2",
                "--easy", "6", "--hard", "6", "--suite-dir", f"{td}/data",
                "--out", f"{td}/proof.md", "--report-dir", f"{td}/runs")
        assert p.returncode == 1, (p.returncode, p.stdout[-400:])
        memo = Path(f"{td}/proof.md").read_text(encoding="utf-8")
        assert "NOT CLEARED" in memo, memo[:400]
        assert "run 1: easy 0/6" in memo, memo[:800]
        assert "gallery" in memo


@check("adapter derives the family from the stem")
def _adapter():
    p = run("tools/bench_adapter.py", "/x/dark-on-dark-0007.png", "--print-family")
    assert p.returncode == 0 and p.stdout.strip() == "dark-on-dark"
    p = run("tools/bench_adapter.py", "/x/cross-shadow-0001.png", "--print-family")
    assert p.stdout.strip() == "cross-shadow"


def main():
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}\n      {e}")
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
