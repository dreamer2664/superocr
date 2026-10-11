#!/usr/bin/env python3
"""bench.py — the scoring harness for superocr (t-20261011-2f3d, JOBS.md S0).

The judge before the player. This file defines three contracts and enforces them:

  1. THE SUITE FORMAT — how labelled images sit on disk (BENCH.md has the
     one-page version for generator authors):

         data/<suite>/manifest.jsonl          one JSON object per line
         data/<suite>/images/...              paths relative to the suite dir

     Manifest fields, all required unless noted:
       id      unique, [A-Za-z0-9][A-Za-z0-9._-]{0,63}
       image   path relative to the suite directory; must exist, non-empty
       label   the exact, case-sensitive answer  ("?" or exclude:true = not scored)
       family  the family this item belongs to (per-family numbers are reported)
       tags    optional list of strings

  2. THE READER PROTOCOL — any reader worth scoring is one command line:
     stdout is the recognised text, the only leniency is ONE trailing newline.
     Use the {image} placeholder, or let the image path be appended:
         --reader "python3 readers/classic.py --image {image}"
         --reader "python3 readers/classic.py"        (path appended)
     A non-zero exit is not a bench crash: the item is recorded as failed with
     the error, and the run continues.

  3. THE REPORT — every run writes reports/<run>.json (canonical, everything
     needed to re-run and to check the number), a matching .md, and a gallery
     of the failures. A number in the README must link to a report file.

Scoring is exact and case-sensitive. Bars come from JOBS.md:
    easy >= 98/100, hard >= 95/100
compared with integer arithmetic (correct*100 >= bar*total) so no float ever
rounds a pass into existence. Excluded items are reported, never hidden, and
never counted as correct. `--runs 3` repeats the whole thing; the bar must be
cleared by ALL runs for the run to count as proof of stability.

Exit codes: 0 = every suite cleared its bar in every run; 1 = it did not;
2 = the bench itself could not run (bad suite, bad manifest, bad arguments).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time

BENCH_VERSION = 1
DEFAULT_SUITES = ("easy", "hard")
# JOBS.md: easy >= 98/100, hard >= 95/100. Percent, exact integer comparison.
DEFAULT_BARS = {"easy": 98, "hard": 95}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
EXCLUDE_LABEL = "?"


class BenchError(Exception):
    """The bench cannot run. Exit 2, message to stderr, no traceback."""


# ---------------------------------------------------------------------------
# clock / ids
# ---------------------------------------------------------------------------

def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def stamp(dt: _dt.datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def run_id(dt: _dt.datetime, index: int, runs: int, suites: list[str]) -> str:
    prefix = "-".join(suites)
    if runs > 1:
        return f"{stamp(dt)}-{prefix}-r{index}of{runs}"
    return f"{stamp(dt)}-{prefix}"


# ---------------------------------------------------------------------------
# suites
# ---------------------------------------------------------------------------

def load_suite(root: str, name: str) -> list[dict]:
    """Read data/<name>/manifest.jsonl. Strict: any doubt is a BenchError."""
    sdir = os.path.join(root, name)
    mpath = os.path.join(sdir, "manifest.jsonl")
    if not os.path.isfile(mpath):
        raise BenchError(
            f"suite '{name}': no manifest at {mpath} "
            f"(is the generator for this suite built yet?)")
    items: list[dict] = []
    seen: set[str] = set()
    with open(mpath, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            where = f"{name}/manifest.jsonl:{lineno}"
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise BenchError(f"{where}: not valid JSON ({e.msg})")
            if not isinstance(rec, dict):
                raise BenchError(f"{where}: expected a JSON object")
            rel = rec.get("image") or rec.get("file")
            if not isinstance(rel, str) or not rel:
                raise BenchError(f"{where}: missing image path (key 'image', alias 'file')")
            iid = rec.get("id")
            if iid is None:
                # forgiving about presentation, exact about content: generators
                # that name items by their file get an id derived from the stem
                stem = os.path.splitext(os.path.basename(rel))[0]
                iid = stem
                if not ID_RE.match(iid):
                    raise BenchError(
                        f"{where}: cannot derive an id from {rel!r} — "
                        f"add an explicit \"id\" field")
            if not isinstance(iid, str) or not ID_RE.match(iid):
                raise BenchError(f"{where}: bad id {iid!r}")
            if iid in seen:
                raise BenchError(f"{where}: duplicate id {iid!r}")
            seen.add(iid)
            path = os.path.join(sdir, rel)
            if not os.path.isfile(path):
                raise BenchError(f"{where}: image not found: {path}")
            if os.path.getsize(path) == 0:
                raise BenchError(f"{where}: image is empty: {path}")
            label = rec.get("label")
            if not isinstance(label, str) or label == "":
                raise BenchError(f"{where}: missing label (use \"?\" to exclude)")
            family = rec.get("family")
            if not isinstance(family, str) or not family:
                raise BenchError(f"{where}: missing family")
            tags = rec.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
                raise BenchError(f"{where}: tags must be a list of strings")
            excluded = bool(rec.get("exclude", False)) or label == EXCLUDE_LABEL
            items.append({
                "id": iid, "image": path, "label": label,
                "family": family, "tags": tags, "excluded": excluded,
            })
    if not items:
        raise BenchError(f"suite '{name}': manifest has no items")
    return items


def resolve_suites(root: str, wanted: list[str]) -> dict[str, list[dict]]:
    out = {}
    for name in wanted:
        out[name] = load_suite(root, name)
    return out


# ---------------------------------------------------------------------------
# reader protocol
# ---------------------------------------------------------------------------

def build_argv(template: str, image: str, item_id: str) -> list[str]:
    parts = shlex.split(template)
    if not parts:
        raise BenchError("empty reader command")
    has_image = any("{image}" in p for p in parts)
    argv = [p.replace("{image}", image).replace("{id}", item_id) for p in parts]
    if not has_image:
        argv.append(image)
    return argv


def normalise_reader_output(raw: bytes) -> str:
    """One trailing newline is plumbing; everything else is exact."""
    text = raw.decode("utf-8", "replace")
    if text.endswith("\r\n"):
        return text[:-2]
    if text.endswith("\n"):
        return text[:-1]
    return text


def run_reader(template: str, item: dict, timeout: float) -> tuple[str, str | None, float]:
    """Returns (text, error, seconds). Never raises for reader-side failures."""
    argv = build_argv(template, item["image"], item["id"])
    started = time.perf_counter()
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "", f"timeout after {timeout:g}s", time.perf_counter() - started
    except OSError as e:
        return "", f"could not run reader: {e}", time.perf_counter() - started
    seconds = time.perf_counter() - started
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:]
        detail = f" (stderr: {tail[0][:200]})" if tail else ""
        return "", f"reader exited {proc.returncode}{detail}", seconds
    return normalise_reader_output(proc.stdout), None, seconds


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def pct(correct: int, total: int) -> float | None:
    return round(100.0 * correct / total, 2) if total else None


def score_suite(name: str, items: list[dict], bar: int, template: str,
                timeout: float, gallery_dir: str | None) -> dict:
    results = []
    for item in items:
        if item["excluded"]:
            # never sent to the reader: a tile nobody can read must not acquire
            # a "got" that someone later points at as a score. Reported by id.
            results.append({
                "id": item["id"], "family": item["family"], "image": item["image"],
                "label": item["label"], "got": None, "error": None,
                "match": None, "excluded": True, "seconds": None,
            })
            continue
        text, error, seconds = run_reader(template, item, timeout)
        match = (error is None and text == item["label"])
        results.append({
            "id": item["id"], "family": item["family"], "image": item["image"],
            "label": item["label"], "got": text, "error": error,
            "match": match, "excluded": False, "seconds": seconds,
        })

    scored = [r for r in results if not r["excluded"]]
    excluded = [r for r in results if r["excluded"]]
    correct = sum(1 for r in scored if r["match"])
    total = len(scored)
    passed = total > 0 and correct * 100 >= bar * total

    families: dict[str, dict] = {}
    for r in scored:
        fam = families.setdefault(r["family"], {"total": 0, "correct": 0, "excluded": 0})
        fam["total"] += 1
        fam["correct"] += int(r["match"])
    for r in excluded:
        fam = families.setdefault(r["family"], {"total": 0, "correct": 0, "excluded": 0})
        fam["excluded"] += 1
    for fam in families.values():
        fam["pct"] = pct(fam["correct"], fam["total"])

    times = [r["seconds"] for r in scored]
    failures = [r for r in scored if not r["match"]]

    gallery = None
    if failures and gallery_dir:
        gallery = write_gallery(gallery_dir, name, failures)

    return {
        "suite": name, "total": total, "correct": correct, "pct": pct(correct, total),
        "bar": bar, "passed": passed,
        "excluded_count": len(excluded),
        "excluded_ids": [r["id"] for r in excluded],
        "families": families,
        "median_s": round(statistics.median(times), 4) if times else None,
        "p95_s": round(sorted(times)[max(0, int(0.95 * len(times)) - 1)], 4) if times else None,
        "failures": failures,
        "gallery": gallery,
        "results": results,
    }


def write_gallery(gdir: str, suite: str, failures: list[dict]) -> str:
    """Copy failing images and write gallery.md — the ugly ones included.

    gdir is the suite's own directory (reports/gallery/<run>/<suite>).
    """
    os.makedirs(gdir, exist_ok=True)
    lines = [f"# failure gallery — {suite} ({len(failures)} items)", ""]
    for r in failures:
        ext = os.path.splitext(r["image"])[1] or ".bin"
        dest = os.path.join(gdir, r["id"] + ext)
        try:
            shutil.copyfile(r["image"], dest)
        except OSError as e:
            dest = f"(could not copy: {e})"
        shown = r["error"] if r["error"] else f"got {r['got']!r}"
        lines.append(f"- `{r['id']}` [{r['family']}] expected {r['label']!r} — {shown} — `{dest}`")
    with open(os.path.join(gdir, "gallery.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return gdir


# ---------------------------------------------------------------------------
# one run, all suites
# ---------------------------------------------------------------------------

def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"],
                             capture_output=True, timeout=10, text=True)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def unique_rid(report_dir: str, rid: str) -> str:
    """Two invocations in the same second must not overwrite each other."""
    suffix = 0
    while True:
        candidate = rid if not suffix else f"{rid}-{suffix + 1}"
        if not (os.path.exists(os.path.join(report_dir, candidate + ".json"))
                or os.path.exists(os.path.join(report_dir, candidate + ".md"))):
            return candidate
        suffix += 1


def one_run(args, suites: dict[str, list[dict]], run_index: int,
            started: _dt.datetime, bars: dict[str, int],
            bar_overridden: bool) -> dict:
    this = utc_now()
    report_dir = os.path.abspath(args.report_dir)
    os.makedirs(report_dir, exist_ok=True)
    rid = unique_rid(report_dir, run_id(this, run_index, args.runs, list(suites.keys())))
    gallery_root = os.path.join(report_dir, "gallery", rid) if args.gallery else None

    scored = {}
    for name, items in suites.items():
        gdir = os.path.join(gallery_root, name) if gallery_root else None
        scored[name] = score_suite(name, items, bars[name], args.reader,
                                   args.timeout, gdir)

    passed = all(s["passed"] for s in scored.values())
    totals = {"total": sum(s["total"] for s in scored.values()),
              "correct": sum(s["correct"] for s in scored.values())}
    totals["pct"] = pct(totals["correct"], totals["total"])
    galleries = {n: s["gallery"] for n, s in scored.items() if s["gallery"]}

    report = {
        "bench": "bench.py", "bench_version": BENCH_VERSION,
        "run_id": rid, "run_index": run_index, "runs": args.runs,
        "started_ts": started.isoformat(timespec="seconds"),
        "finished_ts": this.isoformat(timespec="seconds"),
        "suite_dir": os.path.abspath(args.suite_dir),
        "seed": args.seed,
        "reader": {"command": args.reader,
                   "name": args.reader_name or shlex.split(args.reader)[0]},
        "git_commit": git_commit(),
        "bars": bars, "bar_overridden": bar_overridden,
        "excluded_count": sum(s["excluded_count"] for s in scored.values()),
        "galleries": galleries,
        "totals": totals,
        "suites": scored,
        "passed": passed,
    }

    json_path = os.path.join(report_dir, rid + ".json")
    md_path = os.path.join(report_dir, rid + ".md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_md(report))
    report["report_json"] = json_path
    report["report_md"] = md_path
    return report


def render_md(report: dict) -> str:
    lines = [
        f"# bench report — {report['run_id']}",
        "",
        f"- reader: `{report['reader']['command']}`",
        f"- run: {report['run_index']} of {report['runs']}, seed {report['seed']}"
        + (f", commit `{report['git_commit'][:12]}`" if report["git_commit"] else ""),
        f"- verdict: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "| suite | correct | total | pct | bar | passed | excluded |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in report["suites"].items():
        lines.append(f"| {name} | {s['correct']} | {s['total']} | {s['pct']} "
                     f"| {s['bar']} | {'yes' if s['passed'] else 'NO'} | {s['excluded_count']} |")
    lines += ["", "## by family", ""]
    for name, s in report["suites"].items():
        lines.append(f"### {name}")
        lines.append("| family | correct | total | pct |")
        lines.append("|---|---|---|---|")
        if s["total"] == 0:
            lines.append("")
            lines.append("**nothing was scored in this suite** — every item is "
                         "excluded; an empty suite cannot clear a bar.")
        for fam, f in sorted(s["families"].items()):
            lines.append(f"| {fam} | {f['correct']} | {f['total']} | {f['pct']} |")
        if s["excluded_ids"]:
            lines.append("")
            lines.append(f"excluded (not scored): {', '.join(s['excluded_ids'])}")
        if s["failures"]:
            lines += ["", f"## {name} failures ({len(s['failures'])})", ""]
            for r in s["failures"][:60]:
                shown = r["error"] if r["error"] else f"got {r['got']!r}"
                lines.append(f"- `{r['id']}` [{r['family']}] expected {r['label']!r} — {shown}")
            if len(s["failures"]) > 60:
                lines.append(f"- …and {len(s['failures']) - 60} more (see the JSON and the gallery)")
        lines.append("")
    for name, g in (report.get("galleries") or {}).items():
        lines.append(f"gallery ({name}): `{g}`")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------

def do_validate(args, suites: dict[str, list[dict]]) -> int:
    for name, items in suites.items():
        scored = [i for i in items if not i["excluded"]]
        fams = sorted({i["family"] for i in items})
        print(f"{name}: {len(items)} items, {len(scored)} scored, "
              f"{len(items) - len(scored)} excluded, families: {', '.join(fams)}")
    print("OK: manifests are valid")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="bench.py",
        description="Score any superocr reader against the easy/hard suites. "
                    "See BENCH.md for the suite format and the reader protocol.")
    p.add_argument("--suite-dir", default="data",
                   help="directory holding <suite>/manifest.jsonl (default: data)")
    p.add_argument("--suites", default=",".join(DEFAULT_SUITES),
                   help=f"comma-separated suites (default: {','.join(DEFAULT_SUITES)})")
    p.add_argument("--reader", default=None,
                   help='reader command line, e.g. "python3 readers/classic.py {image}"')
    p.add_argument("--reader-name", default=None,
                   help="label for reports (default: first word of --reader)")
    p.add_argument("--bar", action="append", default=[],
                   help="override a bar, e.g. --bar easy=98 (repeatable; "
                        "overridden runs are marked in the report)")
    p.add_argument("--runs", type=int, default=1,
                   help="repeat the whole bench N times (JOBS proof: 3)")
    p.add_argument("--timeout", type=float, default=30.0,
                   help="per-item reader timeout in seconds (default: 30)")
    p.add_argument("--seed", type=int, default=0,
                   help="recorded in every report; keep fixed for proof runs")
    p.add_argument("--report-dir", default="reports")
    p.add_argument("--no-gallery", dest="gallery", action="store_false", default=True,
                   help="skip copying failing images (the gallery is part of the proof)")
    p.add_argument("--validate", action="store_true",
                   help="only parse and check the manifests, then exit")
    args = p.parse_args(argv)

    suites_wanted = [s.strip() for s in args.suites.split(",") if s.strip()]
    if not suites_wanted:
        print("bench: no suites requested", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("bench: --runs must be >= 1", file=sys.stderr)
        return 2

    bars = dict(DEFAULT_BARS)
    for spec in args.bar:
        suite, _, value = spec.partition("=")
        try:
            bars[suite] = int(value)
        except ValueError:
            print(f"bench: --bar needs suite=percent, got {spec!r}", file=sys.stderr)
            return 2
        if not 0 <= bars[suite] <= 100:
            print(f"bench: --bar {suite} out of range 0..100", file=sys.stderr)
            return 2
    bar_overridden = any(bars.get(k) != DEFAULT_BARS.get(k) for k in suites_wanted)

    try:
        suites = resolve_suites(args.suite_dir, suites_wanted)
    except BenchError as e:
        print(f"bench: {e}", file=sys.stderr)
        return 2

    missing_bar = [s for s in suites_wanted if s not in bars]
    if missing_bar:
        print(f"bench: no bar defined for suite(s) {', '.join(missing_bar)}; "
              f"pass e.g. --bar {missing_bar[0]}=95", file=sys.stderr)
        return 2

    if args.validate:
        return do_validate(args, suites)

    if not args.reader:
        print("bench: --reader is required to score (or use --validate)", file=sys.stderr)
        return 2

    started = utc_now()
    reports = []
    for i in range(1, args.runs + 1):
        report = one_run(args, suites, i, started, bars, bar_overridden)
        reports.append(report)
        verdict = "PASS" if report["passed"] else "FAIL"
        print(f"[{i}/{args.runs}] {report['run_id']}: {verdict}"
              + "".join(
                  f"  {name} {s['correct']}/{s['total']} ({s['pct']}% vs bar {s['bar']})"
                  for name, s in report["suites"].items()))
        for name, s in report["suites"].items():
            if not s["passed"]:
                print(f"        {name}: {len(s['failures'])} failures"
                      f"{'; gallery: ' + s['gallery'] if s['gallery'] else ''}")
        if report.get("report_md"):
            print(f"        report: {report['report_md']}")

    all_passed = all(r["passed"] for r in reports)
    if args.runs > 1:
        stability = {
            "bench_version": BENCH_VERSION, "runs": args.runs,
            "passed_runs": sum(1 for r in reports if r["passed"]),
            "all_passed": all_passed,
            "reader": args.reader, "seed": args.seed,
            "bar_overridden": bar_overridden,
            "per_run": [{"run_id": r["run_id"], "passed": r["passed"],
                         "suites": {n: {"correct": s["correct"], "total": s["total"],
                                        "pct": s["pct"]}
                                    for n, s in r["suites"].items()}}
                        for r in reports],
        }
        os.makedirs(args.report_dir, exist_ok=True)
        s_rid = unique_rid(os.path.abspath(args.report_dir),
                           f"{stamp(started)}-stability")
        spath = os.path.join(args.report_dir, s_rid + ".json")
        with open(spath, "w", encoding="utf-8") as fh:
            json.dump(stability, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"stability: {stability['passed_runs']}/{args.runs} runs passed"
              f" — {'OK for the JOBS proof' if all_passed else 'NOT proof of stability'}")
        print(f"        stability report: {spath}")

    print("VERDICT:", "PASS" if all_passed else "FAIL")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
