#!/usr/bin/env python3
"""Tests for bench.py (t-20261011-2f3d).

What is tested here is the judge itself: scoring math, exactness, exclusions,
the failure gallery, reader crashes and timeouts, and the --runs 3 stability
claim. Stdlib only, offline, seeded, fast — CI runs this on every push.

    python3 -m unittest discover -s tests -v
    python3 tests/test_bench.py          # same thing, direct
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BENCH = os.path.join(ROOT, "bench.py")
FAKE = os.path.join(HERE, "fixtures", "fake_reader.py")


def write_suite(root, name, items, image_bytes=b"pretend this is a PNG"):
    """items: list of dicts with id, label, family, and optional extras."""
    sdir = os.path.join(root, name)
    images = os.path.join(sdir, "images")
    os.makedirs(images, exist_ok=True)
    lines = []
    mapping = {}
    for it in items:
        image_rel = f"images/{it['id']}.png"
        with open(os.path.join(sdir, image_rel), "wb") as fh:
            fh.write(image_bytes)
        rec = {"id": it["id"], "image": image_rel, "label": it["label"],
               "family": it.get("family", "plain")}
        rec.update(it.get("extra", {}))
        lines.append(json.dumps(rec))
        mapping[it["id"]] = it["label"]
    with open(os.path.join(sdir, "manifest.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return mapping


def fake_command(map_path, mode="ok", state=None, fail_on=0, sleep=0.0):
    cmd = (f'{sys.executable} "{FAKE}" --image {{image}} --map "{map_path}" '
           f"--mode {mode}")
    if state:
        cmd += f' --state "{state}"'
    if fail_on:
        cmd += f" --fail-on {fail_on}"
    if sleep:
        cmd += f" --sleep {sleep}"
    return cmd


class BenchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bench-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = os.path.join(self.tmp, "data")
        self.reports = os.path.join(self.tmp, "reports")
        os.makedirs(self.data, exist_ok=True)

    # ---- helpers ---------------------------------------------------------

    def four_good_items(self):
        return [{"id": f"easy-000{i}", "label": f"aB{i}", "family": "plain"}
                for i in range(1, 5)]

    def write_map(self, mapping, name="map.json"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh)
        return path

    def map_for(self, suite, items, name="map.json"):
        """Write a suite and return the PATH to a reader map for it."""
        return self.write_map(write_suite(self.data, suite, items), name)

    def run_bench(self, reader, *extra, suites="easy", timeout=None):
        cmd = [sys.executable, BENCH, "--suite-dir", self.data,
               "--suites", suites, "--reader", reader,
               "--report-dir", self.reports]
        if timeout is not None:
            cmd += ["--timeout", str(timeout)]
        cmd += list(extra)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    def last_report(self):
        names = [n for n in os.listdir(self.reports) if n.endswith(".json")
                 and "stability" not in n]
        newest = max(names, key=lambda n: os.path.getmtime(os.path.join(self.reports, n)))
        with open(os.path.join(self.reports, newest), encoding="utf-8") as fh:
            return json.load(fh)

    # ---- manifest validation --------------------------------------------

    def test_validate_ok(self):
        write_suite(self.data, "easy", self.four_good_items())
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy", "--validate"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("4 items, 4 scored, 0 excluded", p.stdout)

    def test_validate_catches_problems(self):
        cases = {
            "duplicate id": (
                [{"id": "same", "label": "a", "family": "plain"},
                 {"id": "same", "label": "b", "family": "plain"}], "duplicate id"),
            "missing label": (
                [{"id": "x1", "label": "", "family": "plain"}], "missing label"),
            "missing family": (
                [{"id": "x2", "label": "a", "family": ""}], "missing family"),
        }
        for title, (items, expect) in cases.items():
            with self.subTest(title):
                shutil.rmtree(self.data, ignore_errors=True)
                os.makedirs(self.data)
                write_suite(self.data, "easy", items)
                p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                                    "--suites", "easy", "--validate"],
                                   capture_output=True, text=True, timeout=60)
                self.assertEqual(p.returncode, 2)
                self.assertIn(expect, p.stderr)

    def test_missing_image_is_caught(self):
        mapping = write_suite(self.data, "easy", self.four_good_items())
        os.remove(os.path.join(self.data, "easy", "images", "easy-0001.png"))
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy", "--validate"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("image not found", p.stderr)

    def test_missing_suite_is_exit_2(self):
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy,hard", "--validate"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("no manifest", p.stderr)

    def test_unknown_suite_needs_a_bar(self):
        write_suite(self.data, "easy", self.four_good_items())
        write_suite(self.data, "medium", self.four_good_items())
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy,medium", "--validate"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("no bar defined for suite", p.stderr)

    # ---- scoring ---------------------------------------------------------

    def test_all_correct_passes_and_report_schema(self):
        mapping = self.map_for("easy", self.four_good_items())
        p = self.run_bench(fake_command(mapping), "--bar", "easy=50")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("VERDICT: PASS", p.stdout)
        rep = self.last_report()
        for key in ("bench_version", "run_id", "seed", "reader", "bars",
                    "bar_overridden", "totals", "suites", "passed"):
            self.assertIn(key, rep)
        easy = rep["suites"]["easy"]
        self.assertEqual((easy["correct"], easy["total"]), (4, 4))
        self.assertTrue(easy["passed"])
        self.assertEqual(easy["failures"], [])
        self.assertEqual(rep["bar_overridden"], True)   # --bar easy=50 used

    def test_default_bars_are_the_jobs_numbers(self):
        # 4/4 = 100% >= 98 -> PASS, with bar_overridden False (no override used)
        mapping = self.map_for("easy", self.four_good_items())
        p = self.run_bench(fake_command(mapping))
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = self.last_report()
        self.assertEqual(rep["suites"]["easy"]["bar"], 98)
        self.assertEqual(rep["bar_overridden"], False)
        self.assertTrue(rep["suites"]["easy"]["passed"])

    def test_default_bar_fails_a_75_percent_run(self):
        # 3/4 = 75% < 98 -> FAIL, and the report must say so without an override
        mapping = write_suite(self.data, "easy", self.four_good_items())
        bad = dict(mapping)
        bad["easy-0003"] = "not the label"
        p = self.run_bench(fake_command(self.write_map(bad, "bad.json")))
        self.assertEqual(p.returncode, 1)
        rep = self.last_report()
        self.assertEqual(rep["suites"]["easy"]["bar"], 98)
        self.assertFalse(rep["suites"]["easy"]["passed"])

    def test_one_wrong_is_a_failure_with_gallery(self):
        mapping = write_suite(self.data, "easy", self.four_good_items())
        good = {k: v for k, v in mapping.items() if k != "easy-0002"}
        # easy-0002 missing from the map -> the reader exits 4 on that item
        state_map = self.write_map(good, "trimmed.json")
        p = self.run_bench(fake_command(state_map))
        self.assertEqual(p.returncode, 1)
        rep = self.last_report()
        easy = rep["suites"]["easy"]
        self.assertEqual((easy["correct"], easy["total"]), (3, 4))
        fails = {f["id"]: f for f in easy["failures"]}
        self.assertIn("easy-0002", fails)
        self.assertIn("exited 4", fails["easy-0002"]["error"])
        gallery = fails["easy-0002"]["image"] and easy["gallery"]
        self.assertTrue(os.path.isdir(gallery))
        self.assertTrue(os.path.isfile(os.path.join(gallery, "easy-0002.png")))
        with open(os.path.join(gallery, "gallery.md"), encoding="utf-8") as fh:
            self.assertIn("easy-0002", fh.read())

    def test_exactness_newline_lenient_space_strict(self):
        mapping = self.map_for("easy", [{"id": "one", "label": "aB3",
                                         "family": "plain"}])
        p = self.run_bench(fake_command(mapping, mode="ok"))
        self.assertEqual(p.returncode, 0, p.stderr)     # trailing \n tolerated
        p = self.run_bench(fake_command(mapping, mode="space"))
        self.assertEqual(p.returncode, 1)               # trailing space is a MISS
        rep = self.last_report()
        self.assertEqual(rep["suites"]["easy"]["correct"], 0)

    def test_case_sensitivity(self):
        self.map_for("easy", [{"id": "one", "label": "aB3", "family": "plain"}])
        wrong_case = self.write_map({"one": "ab3"}, "case.json")
        p = self.run_bench(fake_command(wrong_case))
        self.assertEqual(p.returncode, 1)

    def test_reader_crash_is_a_failed_item_not_a_bench_crash(self):
        mapping = self.map_for("easy", self.four_good_items())
        p = self.run_bench(fake_command(mapping, mode="crash"))
        self.assertEqual(p.returncode, 1)               # not 2, no traceback
        self.assertNotIn("Traceback", p.stderr)
        rep = self.last_report()
        err = rep["suites"]["easy"]["failures"][0]["error"]
        self.assertIn("exited 3", err)

    def test_timeout_is_recorded(self):
        mapping = self.map_for("easy", [{"id": "slow", "label": "x",
                                         "family": "plain"}])
        p = self.run_bench(fake_command(mapping, mode="sleep", sleep=3),
                           timeout=0.3)
        self.assertEqual(p.returncode, 1)
        rep = self.last_report()
        self.assertIn("timeout", rep["suites"]["easy"]["failures"][0]["error"])

    def test_excluded_items_are_reported_never_scored_never_run(self):
        mapping = self.map_for("easy", [
            {"id": "scored", "label": "ok", "family": "plain"},
            {"id": "unknown", "label": "?", "family": "plain"},
        ])
        p = self.run_bench(fake_command(mapping))
        self.assertEqual(p.returncode, 0, p.stderr)     # 1/1 = 100% >= 98
        rep = self.last_report()
        easy = rep["suites"]["easy"]
        self.assertEqual((easy["correct"], easy["total"]), (1, 1))
        self.assertEqual(easy["excluded_count"], 1)
        self.assertEqual(easy["excluded_ids"], ["unknown"])
        self.assertEqual(rep["excluded_count"], 1)
        # the excluded image must NOT be in the gallery even though it "failed"
        self.assertFalse(easy["gallery"])
        # and it must never have been handed to the reader
        excluded = [r for r in easy["results"] if r["id"] == "unknown"][0]
        self.assertIsNone(excluded["got"])
        self.assertIsNone(excluded["match"])

    def test_families_breakdown_is_per_family(self):
        self.map_for("hard", [
            {"id": "h1", "label": "aa", "family": "snow"},
            {"id": "h2", "label": "bb", "family": "snow"},
            {"id": "h3", "label": "cc", "family": "darts"},
        ])
        state_map = self.write_map({"h1": "aa", "h2": "XX", "h3": "cc"}, "fams.json")
        p = self.run_bench(fake_command(state_map), suites="hard")
        self.assertEqual(p.returncode, 1)
        fams = self.last_report()["suites"]["hard"]["families"]
        self.assertEqual((fams["snow"]["correct"], fams["snow"]["total"]), (1, 2))
        self.assertEqual((fams["darts"]["correct"], fams["darts"]["total"]), (1, 1))

    # ---- runs / stability ------------------------------------------------

    def test_runs_three_reports_and_stability_line(self):
        mapping = self.map_for("easy", self.four_good_items())
        p = self.run_bench(fake_command(mapping), "--runs", "3")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("stability: 3/3 runs passed", p.stdout)
        stability = [n for n in os.listdir(self.reports) if "stability" in n]
        self.assertEqual(len(stability), 1)
        with open(os.path.join(self.reports, stability[0]), encoding="utf-8") as fh:
            st = json.load(fh)
        self.assertEqual((st["runs"], st["passed_runs"], st["all_passed"]), (3, 3, True))
        self.assertEqual(len(st["per_run"]), 3)
        rids = {r["run_id"] for r in st["per_run"]}
        self.assertEqual(len(rids), 3)

    def test_runs_three_one_bad_run_is_not_stable(self):
        mapping = self.map_for("easy", self.four_good_items())
        state = os.path.join(self.tmp, "counter")
        # 4 items per run: read 5 is the FIRST item of run 2, so run 2 alone fails
        p = self.run_bench(
            fake_command(mapping, mode="stateful", state=state, fail_on=5),
            "--runs", "3")
        self.assertEqual(p.returncode, 1)
        stability = [n for n in os.listdir(self.reports) if "stability" in n][0]
        with open(os.path.join(self.reports, stability), encoding="utf-8") as fh:
            st = json.load(fh)
        self.assertEqual((st["runs"], st["passed_runs"], st["all_passed"]), (3, 2, False))
        self.assertEqual([r["passed"] for r in st["per_run"]], [True, False, True])

    # ---- misc ------------------------------------------------------------

    def test_gallery_path_is_the_suite_dir_once(self):
        mapping = write_suite(self.data, "easy", self.four_good_items())
        bad = dict(mapping)
        bad["easy-0001"] = "nope"
        p = self.run_bench(fake_command(self.write_map(bad, "b.json")))
        self.assertEqual(p.returncode, 1)
        gallery = self.last_report()["suites"]["easy"]["gallery"]
        self.assertTrue(gallery.endswith(os.path.join("easy")),
                        f"gallery path looks doubled: {gallery}")
        self.assertTrue(os.path.isfile(os.path.join(gallery, "easy-0001.png")))

    def test_two_runs_in_the_same_second_do_not_overwrite_a_report(self):
        mapping = self.map_for("easy", self.four_good_items())
        cmd = fake_command(mapping)
        for _ in range(2):
            p = self.run_bench(cmd)
            self.assertEqual(p.returncode, 0, p.stderr)
        reports = [n for n in os.listdir(self.reports)
                   if n.endswith(".json") and "stability" not in n]
        self.assertEqual(len(reports), 2, reports)


    # ---- co-op mode (t-20261012-5e8a) ------------------------------------

    def test_lock_refuses_a_second_bench_on_the_same_box(self):
        """A live holder means exit 3 with the holder named, before any item runs."""
        mapping = self.map_for("easy", self.four_good_items())
        state = os.path.join(self.tmp, "reader-state.json")
        holder = os.path.join(self.tmp, "bench.lock")
        with open(holder, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "cmd": "unittest holder",
                       "started": "2026-10-12T00:00:00", "host": "test"}, fh)
        env = dict(os.environ, SUPEROCR_BENCH_LOCK=holder)
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy", "--reader", fake_command(mapping, state=state),
                            "--report-dir", self.reports],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("holds the box lock", p.stderr)
        self.assertFalse(os.path.exists(state),
                         "the reader must never run while the lock is held")

    def test_stale_lock_with_dead_pid_is_reclaimed(self):
        """A crashed bench must not block the box forever."""
        mapping = self.map_for("easy", self.four_good_items())
        holder = os.path.join(self.tmp, "bench.lock")
        # a provably-dead pid: a child we started and reaped
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        with open(holder, "w", encoding="utf-8") as fh:
            json.dump({"pid": proc.pid, "cmd": "crashed", "started": "?", "host": "?"}, fh)
        env = dict(os.environ, SUPEROCR_BENCH_LOCK=holder)
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy", "--reader", fake_command(mapping),
                            "--report-dir", self.reports],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        # and the lock we took is cleaned up on exit
        self.assertFalse(os.path.exists(holder))


    def test_cut_footer_and_lock_release_on_sigterm(self):
        """A killed bench leaves a 'cut' footer and no lock behind."""
        items = [{"id": f"easy-000{i}", "label": f"aB{i}", "family": "plain"}
                 for i in range(1, 4)]
        mapping = self.map_for("easy", items)
        locked = os.path.join(self.tmp, "bench.lock")
        os.makedirs(self.reports, exist_ok=True)
        env = dict(os.environ, SUPEROCR_BENCH_LOCK=locked)
        reader = fake_command(mapping, mode="sleep", sleep=1.0)
        p = subprocess.Popen([sys.executable, BENCH, "--suite-dir", self.data,
                              "--suites", "easy", "--reader", reader,
                              "--report-dir", self.reports],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env)
        partials = None
        for _ in range(120):  # wait for the first item to land
            if not os.path.isdir(self.reports):
                time.sleep(0.25)
                continue
            names = [n for n in os.listdir(self.reports) if n.endswith("-partials.jsonl")]
            if names:
                partials = os.path.join(self.reports, names[0])
                if os.path.exists(partials) and os.path.getsize(partials) > 0:
                    break
            time.sleep(0.25)
        self.assertIsNotNone(partials, "no partials file appeared")
        time.sleep(0.6)
        p.terminate()
        p.wait(timeout=60)
        self.assertNotEqual(p.returncode, 0)
        with open(partials, encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        events = [l for l in lines if l.get("event")]
        self.assertEqual([e["event"] for e in events], ["cut"], lines)
        items_seen = [l for l in lines if "id" in l]
        self.assertGreaterEqual(len(items_seen), 1)
        self.assertEqual(events[0]["counts"]["easy"]["total"], len(items_seen))
        self.assertFalse(os.path.exists(locked), "the lock must not survive a cut")
        self.assertIn("cut", (p.stderr.read() if p.stderr else ""))


    def _procs_with(self, needle):
        """PIDs whose cmdline mentions `needle` (Linux /proc scan)."""
        out = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as fh:
                    cmd = fh.read().decode("utf-8", "replace")
            except OSError:
                continue
            if needle in cmd:
                out.append(int(pid))
        return out

    def test_cut_takes_the_reader_child_with_it(self):
        """No orphan reader: a SIGTERM'd bench kills the running reader child."""
        items = [{"id": f"easy-000{i}", "label": f"aB{i}", "family": "plain"}
                 for i in range(1, 5)]
        mapping = self.map_for("easy", items)
        os.makedirs(self.reports, exist_ok=True)
        locked = os.path.join(self.tmp, "bench.lock")
        env = dict(os.environ, SUPEROCR_BENCH_LOCK=locked)
        reader = fake_command(mapping, mode="sleep", sleep=2.0)
        p = subprocess.Popen([sys.executable, BENCH, "--suite-dir", self.data,
                              "--suites", "easy", "--reader", reader,
                              "--report-dir", self.reports],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env)
        # wait until item 1 landed -> item 2's reader child is now running
        deadline = time.time() + 30
        while time.time() < deadline:
            names = [n for n in os.listdir(self.reports) if n.endswith("-partials.jsonl")]
            if names and os.path.getsize(os.path.join(self.reports, names[0])) > 0:
                break
            time.sleep(0.1)
        time.sleep(0.4)  # let item 2's child start
        self.assertTrue(self._procs_with(self.tmp), "expected a live reader child")
        p.terminate()
        p.wait(timeout=60)
        deadline = time.time() + 5
        kids = self._procs_with(self.tmp)
        while kids and time.time() < deadline:
            time.sleep(0.2)
            kids = self._procs_with(self.tmp)
        self.assertEqual(kids, [], f"orphan reader(s) survived the cut: {kids}")

    def test_no_lock_env_escape_hatch(self):
        mapping = self.map_for("easy", self.four_good_items())
        holder = os.path.join(self.tmp, "bench.lock")
        with open(holder, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "cmd": "holder", "started": "?", "host": "?"}, fh)
        env = dict(os.environ, SUPEROCR_BENCH_LOCK=holder,
                   SUPEROCR_BENCH_NO_LOCK="1")
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy", "--reader", fake_command(mapping),
                            "--report-dir", self.reports],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_four_stamps_are_in_the_report_and_the_markdown(self):
        mapping = self.map_for("easy", self.four_good_items())
        p = self.run_bench(fake_command(mapping), "--scorer", "iris")
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = self.last_report()
        stamps = rep["stamps"]
        self.assertEqual(stamps["scorer"], "iris")
        self.assertTrue(stamps["reader_command"])
        # the gate's exact contract: 64-hex dir hash, env keys, no abs suite_dir
        self.assertRegex(stamps["dir_hash"], r"^[0-9a-f]{64}$")
        for key in ("python", "pillow", "numpy", "cv2"):
            self.assertIsInstance(stamps["env"].get(key), str, (key, stamps["env"]))
            self.assertTrue(stamps["env"][key].strip(), (key, stamps["env"]))
        self.assertNotIn("suite_dir", rep)
        md_path = os.path.join(self.reports, rep["run_id"] + ".md")
        with open(md_path, encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("dir hash", md)
        self.assertIn("scorer", md)
        # same suite dir -> same hash across runs (the stamp is stable)
        p2 = self.run_bench(fake_command(mapping))
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertEqual(stamps["dir_hash"], self.last_report()["stamps"]["dir_hash"])

    def test_dir_hash_matches_the_gate_function_byte_for_byte(self):
        """The gate re-hashes with tools/make_suites.py::dir_hash; ours must agree."""
        self.map_for("easy", self.four_good_items())
        code = (
            "import json, sys; sys.path.insert(0, 'tools'); sys.path.insert(0, '.');"
            "from make_suites import dir_hash; import bench;"
            f"a=dir_hash(__import__('pathlib').Path({self.data!r}));"
            f"b=bench.dir_hash({self.data!r});"
            "print(json.dumps({'upstream': a, 'bench': b}))"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, cwd=ROOT, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(got["upstream"], got["bench"])

    def test_partials_stream_one_line_per_item_plus_a_done_event(self):
        mapping = self.map_for("easy", self.four_good_items())
        p = self.run_bench(fake_command(mapping))
        self.assertEqual(p.returncode, 0, p.stderr)
        partials = [n for n in os.listdir(self.reports) if n.endswith("-partials.jsonl")]
        self.assertEqual(len(partials), 1, partials)
        with open(os.path.join(self.reports, partials[0]), encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        items = [l for l in lines if "event" not in l]
        done = [l for l in lines if l.get("event") == "done"]
        self.assertEqual(len(items), 4, items)
        self.assertEqual([l["id"] for l in items],
                         ["easy-0001", "easy-0002", "easy-0003", "easy-0004"])
        self.assertEqual(items[-1]["correct"], 4)
        self.assertEqual(items[-1]["total"], 4)
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["counts"]["easy"], {"correct": 4, "total": 4})

    def test_file_alias_and_derived_id(self):
        # a generator that names the key 'file' and omits id must still load
        sdir = os.path.join(self.data, "easy")
        os.makedirs(os.path.join(sdir, "images"))
        with open(os.path.join(sdir, "images", "snow.jpg"), "wb") as fh:
            fh.write(b"x")
        with open(os.path.join(sdir, "manifest.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"file": "images/snow.jpg", "label": "aB3",
                                 "family": "plain", "seed": 42}) + "\n")
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy", "--validate"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        # and a stem that cannot be an id must be refused, not guessed
        with open(os.path.join(sdir, "images", "two words.jpg"), "wb") as fh:
            fh.write(b"x")
        with open(os.path.join(sdir, "manifest.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"file": "images/two words.jpg", "label": "b",
                                 "family": "plain"}) + "\n")
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy", "--validate"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("add an explicit", p.stderr)

    def test_reader_required_to_score(self):
        write_suite(self.data, "easy", self.four_good_items())
        p = subprocess.run([sys.executable, BENCH, "--suite-dir", self.data,
                            "--suites", "easy"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("--reader is required", p.stderr)

    def test_variable_length_labels_and_spaces(self):
        mapping = self.map_for("easy", [
            {"id": "sp", "label": "two words", "family": "plain"},
            {"id": "dig", "label": "A1b2C3", "family": "plain"},
        ])
        p = self.run_bench(fake_command(mapping))
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
