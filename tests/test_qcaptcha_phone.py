#!/usr/bin/env python3
"""qcaptcha phone pipeline tests — real subprocesses against a FAKE adb.

What this proves without a phone in CI:
  * device selection: ok / unauthorized / none / several
  * screencap PNG -> PIL, UI dump -> widget tree -> captcha + text box found
  * the study command writes its folder and types NOTHING
  * solve-once: read-only by default; with --type it TAPS the field, TYPES the
    answer, and VERIFIES by re-dumping the hierarchy
  * duplicates are never typed twice; a captcha that is only inside a WebView
    falls back to vision; nothing-found is an honest error
  * the watch loop stops itself after repeated real errors

Run: python3 tests/test_qcaptcha_phone.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps" / "qcaptcha"
sys.path.insert(0, str(APP))

FIXTURE = ROOT / "tests" / "fixtures" / "fake_adb"


class _Base(unittest.TestCase):
    """Every test gets a private fake-adb state dir and a fresh Adb object."""

    def setUp(self):
        from qcaptcha import phone as phone_mod
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        os.environ["FAKE_ADB_STATE"] = str(self.state)
        for k in ("FAKE_ADB_MODE", "FAKE_ADB_XML", "FAKE_ADB_BAD_VERIFY",
                  "FAKE_ADB_FAIL_SCREENCAP"):
            os.environ.pop(k, None)
        os.chmod(FIXTURE, 0o755)
        self.phone = phone_mod
        self.adb = phone_mod.Adb(adb=str(FIXTURE))

    def tearDown(self):
        self.tmp.cleanup()

    # helpers -------------------------------------------------------------
    def calls(self) -> list[str]:
        p = self.state / "calls.log"
        return p.read_text().splitlines() if p.is_file() else []

    def taps(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("tap")]

    def typed(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("text")]

    def field_text(self) -> str:
        p = self.state / "typed.txt"
        return p.read_text() if p.is_file() else ""


class FakeReader:
    backend = "gemini"

    def __init__(self, text="sUM 34", conf=None):
        self.text, self.conf, self.calls = text, conf, 0

    def read_with_retry(self, img, retry_upscale=True):
        self.calls += 1
        return {"text": self.text, "conf": self.conf, "retried": False,
                "attempts": 1, "backend": self.backend}

    def read_page(self, shot, hint=None):
        raise AssertionError("phone pipeline must not call read_page")


class FakeClient:
    """Stands in for the Gemini client: one canned solve_page JSON."""

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def generate(self, parts, **kw):
        self.calls += 1
        return self.reply


class TestEscaping(unittest.TestCase):
    def test_input_text_quoting(self):
        from qcaptcha.phone import esc_input_text
        self.assertEqual(esc_input_text("ab cd"), "'ab%scd'")
        self.assertEqual(esc_input_text("it's"), "'it'\\''s'")
        self.assertEqual(esc_input_text("a&b|c"), "'a&b|c'")


class TestDeviceSelection(_Base):
    def test_one_device_ok(self):
        d = self.adb.pick()
        self.assertEqual(d["state"], "device")
        self.assertEqual(d["masked"], "FAKE…")

    def test_none_connected(self):
        os.environ["FAKE_ADB_MODE"] = "none"
        with self.assertRaises(self.phone.AdbError) as cm:
            self.adb.pick()
        self.assertIn("no device connected", str(cm.exception))
        self.assertIn("USB debugging", str(cm.exception))

    def test_unauthorized_is_actionable(self):
        os.environ["FAKE_ADB_MODE"] = "unauthorized"
        with self.assertRaises(self.phone.AdbError) as cm:
            self.adb.pick()
        self.assertIn("accept the USB-debugging prompt", str(cm.exception))

    def test_two_devices_need_serial(self):
        os.environ["FAKE_ADB_MODE"] = "two"
        with self.assertRaises(self.phone.AdbError) as cm:
            self.adb.pick()
        self.assertIn("--serial", str(cm.exception))

    def test_bad_adb_path_is_actionable(self):
        adb = self.phone.Adb(adb="/nonexistent/adb")
        rep = self.phone.check(adb)
        self.assertFalse(rep["ok"])
        self.assertIn("platform-tools", rep["error"])


class TestCaptureAndDump(_Base):
    def test_screencap_png(self):
        img = self.adb.screencap()
        self.assertEqual(img.size, (1080, 2400))
        self.assertEqual(img.mode, "RGB")

    def test_ui_dump_to_tree(self):
        nodes = self.phone.parse_ui_dump(self.adb.dump_ui())
        classes = [n["class"] for n in nodes]
        self.assertTrue(any("ImageView" in c for c in classes))
        self.assertTrue(any("EditText" in c for c in classes))
        edit = [n for n in nodes if "EditText" in n["class"]][0]
        self.assertEqual(edit["bounds"], [100, 760, 780, 100])
        self.assertEqual(nodes[0]["depth"], 0)

    def test_analyze_finds_captcha_above_input(self):
        nodes = self.phone.parse_ui_dump(self.adb.dump_ui())
        an = self.phone.analyze_ui(nodes, (1080, 2400))
        self.assertEqual(an["captcha"], [100, 400, 780, 300])
        self.assertEqual(an["input"], [100, 760, 780, 100])
        self.assertEqual(an["notes"], [])

    def test_webview_screen_says_so(self):
        os.environ["FAKE_ADB_XML"] = "webview"
        nodes = self.phone.parse_ui_dump(self.adb.dump_ui())
        an = self.phone.analyze_ui(nodes, (1080, 2400))
        self.assertIsNone(an["captcha"])
        self.assertTrue(any("WebView" in n for n in an["notes"]))
        self.assertTrue(any("vision fallback" in n for n in an["notes"]))

    def test_screen_size_and_props(self):
        self.assertEqual(self.adb.screen_size(), (1080, 2400))
        self.assertEqual(self.adb.prop("ro.build.version.release"), "13")
        app = self.adb.current_app()
        self.assertEqual(app["package"], "com.example.app")


class TestCheck(_Base):
    def test_check_ok_report(self):
        rep = self.phone.check(self.adb)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["screen"], "1080x2400")
        self.assertIn("ok 1080x2400", rep["screencap"])
        self.assertIn("ok", rep["ui_dump"])
        self.assertEqual(rep["foreground"], "com.example.app/com.example.app.MainActivity")
        self.assertEqual(rep["serial"], "FAKE…")
        self.assertNotIn("FAKE12345678", json.dumps(rep))       # serial masked


class TestStudy(_Base):
    def test_study_writes_folder_and_types_nothing(self):
        out = Path(self.tmp.name) / "study"
        info = self.phone.study(self.adb, out)
        files = set(info["files"])
        self.assertEqual(files, {"ui.xml", "screenshot.png", "study.json",
                                 "REPORT.md", "captcha_crop.png"})
        self.assertEqual(info["candidates"]["captcha"], [100, 400, 780, 300])
        self.assertEqual(info["candidates"]["input"], [100, 760, 780, 100])
        report = (out / "REPORT.md").read_text()
        self.assertIn("captcha box", report)
        self.assertIn("com.example.app", report)
        data = json.loads((out / "study.json").read_text())
        self.assertTrue(any(n["class"].endswith("EditText") for n in data["nodes"]))
        self.assertEqual(self.taps(), [])                        # nothing touched
        self.assertEqual(self.typed(), [])

    def test_study_no_shot(self):
        out = Path(self.tmp.name) / "study2"
        info = self.phone.study(self.adb, out, shot=False)
        self.assertNotIn("screenshot.png", info["files"])
        self.assertIn("captcha_crop.png", info["files"])

    def test_study_masks_serial(self):
        out = Path(self.tmp.name) / "study3"
        self.phone.study(self.adb, out, shot=False)
        text = (out / "REPORT.md").read_text()
        self.assertIn("FAKE…", text)
        self.assertNotIn("FAKE12345678", text)


class TestSolveOnce(_Base):
    def _solver(self, reader=None, client=None):
        from qcaptcha import config as config_mod
        cfg = config_mod.validate({})
        hist = Path(self.tmp.name) / "hist.csv"
        return self.phone.PhoneSolver(cfg, self.adb, reader or FakeReader(),
                                      client=client, history=hist)

    def test_read_only_by_default(self):
        s = self._solver()
        row = s.solve_once()
        self.assertEqual(row["text"], "sUM 34")
        self.assertEqual(row["mode"], "read-only")
        self.assertFalse(row["delivered"])
        self.assertIsNone(row["error"])
        self.assertEqual(row["detect"], "ui-dump")
        self.assertEqual(self.taps(), [])
        self.assertEqual(self.typed(), [])

    def test_type_types_and_verifies(self):
        s = self._solver()
        row = s.solve_once(type_it=True)
        self.assertTrue(row["delivered"])
        self.assertTrue(row["verified"])
        self.assertEqual(row["error"], None)
        self.assertEqual(self.taps(), ["tap 490 810"])           # centre of the field
        self.assertEqual(len(self.typed()), 1)
        self.assertEqual(self.field_text(), "sUM 34")
        self.assertEqual(row["mode"], "input")

    def test_type_with_failing_verify_is_reported(self):
        os.environ["FAKE_ADB_BAD_VERIFY"] = "1"
        s = self._solver()
        row = s.solve_once(type_it=True)
        self.assertTrue(row["delivered"])
        self.assertFalse(row["verified"])
        self.assertIn("not verified", row["error"])

    def test_duplicate_is_not_typed_twice(self):
        s = self._solver()
        first = s.solve_once(type_it=True)
        self.assertTrue(first["delivered"])
        second = s.solve_once(type_it=True)
        self.assertIn("duplicate", second["error"])
        self.assertEqual(len(self.typed()), 1)                    # still only one
        self.assertEqual(len(self.taps()), 1)

    def test_webview_falls_back_to_vision(self):
        os.environ["FAKE_ADB_XML"] = "webview"
        reply = ('{"captcha_box_2d":[167,93,292,815],"input_box_2d":[317,93,358,815],'
                 '"text":"VISION7"}')
        cl = FakeClient(reply)
        reader = FakeReader()
        s = self._solver(reader=reader, client=cl)
        row = s.solve_once(type_it=True)
        self.assertEqual(row["detect"], "vision")
        self.assertEqual(row["text"], "VISION7")                  # model text reused
        self.assertEqual(cl.calls, 1)
        self.assertEqual(reader.calls, 0)                         # no double-read
        self.assertTrue(row["delivered"])
        self.assertEqual(self.field_text(), "VISION7")

    def test_nothing_found_is_honest(self):
        os.environ["FAKE_ADB_XML"] = "empty"
        s = self._solver()
        row = s.solve_once(type_it=True)
        self.assertIn("no captcha found", row["error"])
        self.assertFalse(row["delivered"])
        self.assertEqual(self.typed(), [])

    def test_empty_read_reported(self):
        s = self._solver(reader=FakeReader(text=""))
        row = s.solve_once(type_it=True)
        self.assertIn("empty read", row["error"])
        self.assertEqual(self.typed(), [])

    def test_history_row_written(self):
        s = self._solver()
        s.solve_once(type_it=True)
        hist = Path(self.tmp.name) / "hist.csv"
        text = hist.read_text()
        self.assertIn("sUM 34", text)
        self.assertIn("phone", text)                              # target column

    def test_screencap_failure_is_an_adb_error(self):
        os.environ["FAKE_ADB_FAIL_SCREENCAP"] = "1"
        s = self._solver()
        row = s.solve_once()
        self.assertIn("adb:", row["error"])


class TestLoop(_Base):
    def test_loop_stops_after_repeated_errors(self):
        os.environ["FAKE_ADB_FAIL_SCREENCAP"] = "1"
        from qcaptcha import config as config_mod
        cfg = config_mod.validate({"interval_ms": 250})
        s = self.phone.PhoneSolver(cfg, self.adb, FakeReader(),
                                   history=Path(self.tmp.name) / "h.csv")
        events = []
        s.run_loop(events.append, interval_ms=250, stop_after_errors=3)
        self.assertTrue(any(e.get("_stopped") for e in events))
        self.assertEqual(len(events), 4)                          # 3 tries + stop

    def test_loop_solves_then_stops_on_cycles(self):
        from qcaptcha import config as config_mod
        cfg = config_mod.validate({"interval_ms": 250})
        s = self.phone.PhoneSolver(cfg, self.adb, FakeReader(),
                                   history=Path(self.tmp.name) / "h.csv")
        events = []
        s.run_loop(events.append, interval_ms=250, max_cycles=2)
        self.assertEqual(len(events), 2)
        self.assertTrue(events[0].get("delivered"))               # 1st: solved + typed
        self.assertIn("duplicate", events[1].get("error", ""))    # same screen: untouched
        self.assertEqual(len(self.typed()), 1)


class TestLauncherIntegration(_Base):
    """The flags the user actually types must work end to end (fake adb)."""

    def _run(self, *args):
        env = {**os.environ, "FAKE_ADB_STATE": str(self.state)}
        return subprocess.run(
            [sys.executable, str(APP / "launcher.py"), *args,
             "--adb", str(FIXTURE), "--config", str(Path(self.tmp.name) / "cfg.json")],
            capture_output=True, text=True, timeout=180, env=env)

    def test_phone_check_json(self):
        p = self._run("--phone-check")
        self.assertEqual(p.returncode, 0, p.stderr[-300:])
        rep = json.loads(p.stdout)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["version"].split()[0], "Android")

    def test_phone_study_json_and_folder(self):
        out = Path(self.tmp.name) / "study-launcher"
        p = self._run("--phone-study", "--study-dir", str(out))
        self.assertEqual(p.returncode, 0, p.stderr[-300:])
        info = json.loads(p.stdout)
        self.assertEqual(info["candidates"]["captcha"], [100, 400, 780, 300])
        self.assertTrue((out / "REPORT.md").is_file())

    def test_phone_once_reads_without_typing(self):
        p = self._run("--phone-once", "--reader", "local", "--engine", str(ROOT))
        self.assertEqual(p.returncode, 0, p.stderr[-300:])
        row = json.loads(p.stdout)
        self.assertEqual(row["mode"], "read-only")
        self.assertEqual(self.typed(), [])

    def test_phone_check_reports_missing_adb_cleanly(self):
        p = self._run("--phone-check")
        self.assertEqual(p.returncode, 0)
        env = {**os.environ, "FAKE_ADB_STATE": str(self.state)}
        p2 = subprocess.run(
            [sys.executable, str(APP / "launcher.py"), "--phone-check",
             "--adb", "/nonexistent/adb",
             "--config", str(Path(self.tmp.name) / "cfg.json")],
            capture_output=True, text=True, timeout=180, env=env)
        self.assertEqual(p2.returncode, 3)
        self.assertIn("platform-tools", json.loads(p2.stdout)["error"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
