#!/usr/bin/env python3
"""three_run_proof.py — run bench.py N times and write the truth report (S5).

t-20261011-b0cb. JOBS.md wants proof, not a claim: three consecutive runs, each
clearing the bar, with the numbers and a failure gallery - and if a family
misses the bar, the report says so, with numbers, in the same tone.

    python3 tools/three_run_proof.py --reader "python3 tools/bench_adapter.py {image}"

What it does:
  1. builds data/<suite> with tools/make_suites.py if it is not there yet,
  2. runs bench.py --runs N (default 3) with your reader template,
  3. reads the run reports and writes reports/three-run-proof.md: every run's
     correct/total against the bar, the stability verdict, the per-family
     breakdown and the gallery of the ugly cases.

Exit: 0 = every run cleared every bar; 1 = the bar was NOT cleared somewhere
(the memo names run, suite and the gap); 2 = the proof itself could not run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render_proof(runs: list[dict], reader: str, rdir: Path, suite_dir: Path,
                 stamp: str, stab_file: Path | None = None,
                 note: str | None = None) -> str:
    suites = list(runs[0]["suites"].keys())
    cleared = all(r["passed"] for r in runs)
    L: list[str] = []
    L.append(f"# three-run proof — superocr (S5, t-20261011-b0cb)")
    L.append("")
    if note:
        L.append(f"> {note}")
        L.append("")
    L.append(f"- produced: {stamp} (UTC) · commit `{(runs[0].get('git_commit') or 'unknown')[:12]}`")
    L.append(f"- reader: `{reader}`")
    L.append(f"- suites: `{suite_dir}` · seed {runs[0]['seed']} · "
             f"bars easy >= {runs[0]['bars'].get('easy')}%, hard >= {runs[0]['bars'].get('hard')}%")
    L.append(f"- runs: {len(runs)} consecutive full passes · "
             f"raw reports + galleries: `{rdir.relative_to(ROOT) if str(rdir).startswith(str(ROOT)) else rdir}/`")
    if stab_file:
        L.append(f"- bench's own stability file: `{stab_file.name}`")
    L.append(f"- all items excluded in a suite means nothing was scored; excluded ids are "
             f"listed per suite ({sum(s['excluded_count'] for r in runs for s in r['suites'].values())} across runs)")
    L.append("")
    L.append("## The claim")
    L.append("")
    if cleared:
        L.append("**CLEARED.** Every run cleared every bar. The stability claim "
                 "(JOBS.md, three consecutive runs) holds for this reader.")
    else:
        L.append("**NOT CLEARED.** At least one run missed at least one bar. "
                 "The numbers below are the truth as measured, not a draft. "
                 "Re-run this proof when stronger readers land; the gap is named per line.")
    L.append("")
    for r in runs:
        if not r["passed"]:
            for name, s in r["suites"].items():
                if not s["passed"]:
                    L.append(f"- run {r['run_index']}: {name} {s['correct']}/{s['total']} "
                             f"= {s['pct']}% < bar {s['bar']}%")
    L.append("")
    L.append("## the runs")
    L.append("")
    header = "| run | " + " | ".join(f"{n} (bar {runs[0]['bars'][n]})" for n in suites) + " | verdict | slowest p95 |"
    L.append(header)
    L.append("|" + "---|" * (len(suites) + 3))
    for r in runs:
        cells = []
        for n in suites:
            s = r["suites"][n]
            cells.append(f"{s['correct']}/{s['total']} ({s['pct']}%) {'✓' if s['passed'] else 'NO'}")
        p95 = max((r["suites"][n].get("p95_s") or 0) for n in suites)
        L.append(f"| {r['run_index']} | " + " | ".join(cells) +
                 f" | {'PASS' if r['passed'] else 'FAIL'} | {p95:.2f}s |")
    L.append("")
    L.append("## by family (last run) — and how far each moved across runs")
    L.append("")
    byfam: dict[str, dict[str, list[int]]] = {}
    for r in runs:
        for n, s in r["suites"].items():
            for fam, f in s["families"].items():
                key = f"{n}/{fam}"
                byfam.setdefault(key, {})
                byfam[key].setdefault("correct", []).append(f["correct"])
                byfam[key]["total"] = f["total"]
    L.append("| suite/family | correct (last run) | total | across runs |")
    L.append("|---|---|---|---|")
    for key in sorted(byfam):
        v = byfam[key]
        across = " / ".join(str(c) for c in v["correct"])
        L.append(f"| {key} | {v['correct'][-1]} | {v['total']} | {across} |")
    L.append("")
    L.append("## the ugly cases (gallery)")
    L.append("")
    for r in runs:
        for n, s in r["suites"].items():
            fails = s.get("failures") or []
            g = s.get("gallery")
            ids = ", ".join(f["id"] for f in fails[:10]) + (" …" if len(fails) > 10 else "")
            L.append(f"- run {r['run_index']} {n}: {len(fails)} failure(s)"
                     + (f" — gallery `{g}`" if g else "")
                     + (f" — first: {ids}" if fails else ""))
    L.append("")
    L.append("## re-run this")
    L.append("")
    L.append("```")
    L.append(f"python3 tools/make_suites.py --seed {runs[0]['seed']}   # if data/ is missing")
    L.append(f"python3 tools/three_run_proof.py --reader \"{reader}\" --runs {len(runs)}")
    L.append("```")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reader", required=True,
                    help="reader command template, exactly as bench.py takes it")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--suite-dir", default="data")
    ap.add_argument("--easy", type=int, default=100)
    ap.add_argument("--hard", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=None,
                    help="memo path (default reports/three-run-proof.md)")
    ap.add_argument("--report-dir", default=None,
                    help="run files (default reports/three-run-<stamp>/)")
    ap.add_argument("--note", default=None,
                    help="one honest line for the memo header, e.g. 'baseline run, "
                         "not the acceptance proof'")
    a = ap.parse_args(argv)

    suite_dir = Path(a.suite_dir)
    if not suite_dir.is_absolute():
        suite_dir = ROOT / suite_dir
    if not all((suite_dir / s / "manifest.jsonl").exists() for s in ("easy", "hard")):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "make_suites.py"),
                            "--easy", str(a.easy), "--hard", str(a.hard),
                            "--seed", str(a.seed), "--out", str(suite_dir)],
                           cwd=str(ROOT), text=True)
        if r.returncode != 0:
            print("three_run_proof: make_suites.py failed", file=sys.stderr)
            return 2

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rdir = Path(a.report_dir) if a.report_dir else (ROOT / "reports" / f"three-run-{stamp}")
    rdir.mkdir(parents=True, exist_ok=True)
    bench = subprocess.run([sys.executable, str(ROOT / "bench.py"),
                            "--suite-dir", str(suite_dir), "--reader", a.reader,
                            "--runs", str(a.runs), "--seed", str(a.seed),
                            "--report-dir", str(rdir)],
                           cwd=str(ROOT), text=True, capture_output=True)
    sys.stdout.write(bench.stdout)
    sys.stderr.write(bench.stderr)
    if bench.returncode not in (0, 1):
        print(f"three_run_proof: bench.py could not run (exit {bench.returncode})",
              file=sys.stderr)
        return 2

    reports = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(rdir.glob("*.json"))]
    runs = [r for r in reports if "run_index" in r and "suites" in r]
    runs.sort(key=lambda r: r.get("run_index", 0))
    runs = runs[-a.runs:]
    if not runs:
        print("three_run_proof: no run reports found", file=sys.stderr)
        return 2

    stab_file = next(iter(sorted(rdir.glob("*stability*.json"))), None)
    memo = render_proof(runs, a.reader, rdir, suite_dir, stamp, stab_file, a.note)
    out = Path(a.out) if a.out else (ROOT / "reports" / "three-run-proof.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(memo, encoding="utf-8")
    print(f"proof written: {out} ({len(runs)} runs; raw reports in {rdir})")
    return 0 if all(r["passed"] for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
