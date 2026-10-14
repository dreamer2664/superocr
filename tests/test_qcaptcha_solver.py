#!/usr/bin/env python3
"""qcaptcha core tests — headless, no display needed.

Run: python3 tests/test_qcaptcha_solver.py
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps" / "qcaptcha"
sys.path.insert(0, str(APP))

from PIL import Image  # noqa: E402

from qcaptcha import config as config_mod  # noqa: E402
from qcaptcha import injection as injection_mod  # noqa: E402
from qcaptcha import solver as solver_mod  # noqa: E402


class TestConfig(unittest.TestCase):
    def test_defaults_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cfg.json"
            cfg = config_mod.load(p)
            self.assertIsNone(cfg["captcha_region"])
            cfg["captcha_region"] = [10, 20, 160, 60]
            cfg["target_region"] = [300, 400, 200, 30]
            cfg["interval_ms"] = 2000
            config_mod.save(cfg, p)
            back = config_mod.load(p)
            self.assertEqual(back["captcha_region"], [10, 20, 160, 60])
            self.assertEqual(back["interval_ms"], 2000)

    def test_validation_rejects_bad_region(self):
        with self.assertRaises(ValueError):
            config_mod.validate({"captcha_region": [1, 2, 3]})
        with self.assertRaises(ValueError):
            config_mod.validate({"captcha_region": [1, 2, 4, 60]})  # w too small
        with self.assertRaises(ValueError):
            config_mod.validate({"paste_mode": "telepathy"})

    def test_corrupt_file_raises_value_error_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cfg.json"
            p.write_text("{not json")
            with self.assertRaises(ValueError):
                config_mod.load(p)


class FakeEngine:
    """Deterministic engine double for solver-logic tests."""

    def __init__(self, results=None):
        self.results = list(results or [{"text": "Amber42", "conf": 0.9,
                                         "retried": False, "attempts": 1}])
        self.calls = 0

    def read_with_retry(self, img, retry_upscale=True):
        self.calls += 1
        return self.results.pop(0) if self.results else {"text": "", "conf": 0.0,
                                                         "retried": True, "attempts": 2}


class TestSolver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hist = Path(self.tmp.name) / "hist.csv"
        self.cfg = config_mod.validate({
            "captcha_region": [10, 10, 160, 60],
            "target_region": [200, 200, 200, 30],
        })

    def tearDown(self):
        self.tmp.cleanup()

    def _solver(self, engine, capture=None, deliver=None):
        return solver_mod.Solver(
            self.cfg, engine,
            capture_fn=capture or (lambda r: Image.new("RGB", (160, 60), "white")),
            deliver_fn=deliver or (lambda text, reg, **kw: {"delivered": True,
                                                            "mode_used": "paste"}),
            history=self.hist)

    def test_read_once_delivers_and_logs(self):
        delivered = {}
        def deliver(text, reg, **kw):
            delivered.update(text=text, region=list(reg), kw=kw)
            return {"delivered": True, "mode_used": "paste"}
        s = self._solver(FakeEngine([{"text": "Amber42", "conf": 0.9,
                                      "retried": False, "attempts": 1}]), deliver=deliver)
        row = s.read_once()
        self.assertEqual(row["text"], "Amber42")
        self.assertTrue(row["delivered"])
        self.assertEqual(delivered["region"], [200, 200, 200, 30])
        self.assertEqual(delivered["kw"]["mode"], "paste")
        self.assertIsInstance(row["ms"], float)
        self.assertGreaterEqual(row["ms"], 0.0)
        # CSV row written with the same text
        with self.hist.open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "Amber42")
        self.assertEqual(rows[0]["delivered"], "True")

    def test_uncalibrated_captcha_logs_error(self):
        cfg = config_mod.validate({"target_region": [1, 2, 200, 30]})
        s = solver_mod.Solver(cfg, FakeEngine(), capture_fn=lambda r: Image.new("RGB", (5, 5)),
                              deliver_fn=lambda *a, **k: {"delivered": True},
                              history=self.hist)
        row = s.read_once()
        self.assertIn("captcha region not calibrated", row["error"])
        self.assertFalse(row["delivered"])

    def test_empty_read_reported_not_delivered(self):
        s = self._solver(FakeEngine([{"text": "", "conf": 0.0, "retried": True, "attempts": 2}]))
        row = s.read_once()
        self.assertEqual(row["text"], "")
        self.assertIn("empty read", row["error"])
        self.assertFalse(row["delivered"])

    def test_skip_duplicates(self):
        self.cfg["skip_duplicates"] = True
        eng = FakeEngine([{"text": "Amber42", "conf": 0.9, "retried": False, "attempts": 1},
                          {"text": "Amber42", "conf": 0.9, "retried": False, "attempts": 1}])
        s = self._solver(eng)
        r1 = s.read_once()
        r2 = s.read_once()
        self.assertTrue(r1["delivered"])
        self.assertIn("duplicate", r2["error"])

    def test_clean_text(self):
        self.assertEqual(solver_mod.clean_text("  A m  b e r\n"), "A m b e r")
        self.assertEqual(solver_mod.clean_text("\t\n"), "")


class TestInjection(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.backup = dict(injection_mod.BACKENDS)
        def click(x, y):
            self.calls.append(("click", x, y))
        def chord():
            self.calls.append(("chord",))
        def type_text(t):
            self.calls.append(("type", t))
        def sleep(s):
            self.calls.append(("sleep", round(s, 3)))
        self.fake_cb = _FakeClipboard(["old-clip"])
        injection_mod.BACKENDS.update(click=click, paste_chord=chord, type_text=type_text,
                                      sleep=sleep, clipboard=self.fake_cb)

    def tearDown(self):
        injection_mod.BACKENDS.update(self.backup)

    def test_paste_mode_order_and_clipboard_restore(self):
        info = injection_mod.deliver("Amber42", [100, 100, 200, 30], mode="paste",
                                     restore_clipboard=True)
        kinds = [c[0] for c in self.calls]
        self.assertEqual(kinds, ["click", "sleep", "chord", "sleep"])
        self.assertEqual(self.calls[0], ("click", 200, 115))  # center of the box
        self.assertTrue(info["delivered"])
        self.assertTrue(info["clipboard_used"])
        # clipboard was set then restored (restore runs in a short-lived thread)
        deadline = time.time() + 2.0
        while time.time() < deadline and not info.get("restored"):
            time.sleep(0.02)
        self.assertTrue(info.get("restored"))
        self.assertEqual(self.fake_cb.current, "old-clip")

    def test_type_mode_when_no_clipboard(self):
        self.fake_cb.fail_set = True
        info = injection_mod.deliver("Amber42", [0, 0, 50, 20], mode="paste")
        kinds = [c[0] for c in self.calls]
        self.assertIn("type", kinds)
        self.assertEqual(info["mode_used"], "type")
        self.assertTrue(info["delivered"])

    def test_click_failure_raises(self):
        injection_mod.BACKENDS["click"] = lambda x, y: (_ for _ in ()).throw(RuntimeError("no backend"))
        with self.assertRaises(injection_mod.InjectError):
            injection_mod.deliver("x", [0, 0, 20, 20])


class _FakeClipboard:
    def __init__(self, initial):
        self.current = initial[0] if initial else None
        self.fail_set = False

    def get(self):
        return self.current

    def set(self, text):
        if self.fail_set:
            return False
        self.current = text
        return True


class TestSolverLoop(unittest.TestCase):
    def test_loop_runs_n_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config_mod.validate({"captcha_region": [0, 0, 50, 20],
                                       "target_region": [60, 0, 80, 20], "interval_ms": 250})
            eng = FakeEngine([{"text": f"t{i}", "conf": 0.5, "retried": False, "attempts": 1}
                              for i in range(4)])
            s = solver_mod.Solver(cfg, eng, capture_fn=lambda r: Image.new("RGB", (50, 20)),
                                  deliver_fn=lambda *a, **k: {"delivered": True, "mode_used": "paste"},
                                  history=Path(tmp) / "h.csv")
            events = []
            s.run_loop(events.append, interval_ms=250, max_reads=3)
            self.assertEqual(len(events), 3)
            self.assertEqual([e["text"] for e in events], ["t0", "t1", "t2"])


class TestEngineReal(unittest.TestCase):
    """Real engine wiring: generate a captcha with the repo generator, read it
    through the shipping route. Slow (~3s/read) but the whole point."""

    def test_selftest_smoke(self):
        from qcaptcha import engine as engine_mod
        eng = engine_mod.ReaderEngine(ROOT)
        res = eng.selftest(n=2)
        self.assertEqual(res["n"], 2)
        self.assertIn("SMOKE", res["note"])
        self.assertGreaterEqual(res["exact"], 1)  # in-distribution easy reads should land

    def test_read_matches_generated_label(self):
        from qcaptcha import engine as engine_mod
        eng = engine_mod.ReaderEngine(ROOT)
        img, label = eng.generate_sample(424242, "easy")
        text, conf = eng.read(img)
        self.assertTrue(text)
        self.assertGreater(conf, 0.0)


class TestLauncherCLI(unittest.TestCase):
    def test_check_exit_zero(self):
        p = subprocess.run([sys.executable, str(APP / "launcher.py"), "--check"],
                           capture_output=True, text=True, cwd=str(ROOT), timeout=120)
        self.assertEqual(p.returncode, 0, msg=p.stderr)
        rep = json.loads(p.stdout)
        self.assertIn("engine_root", rep)
        self.assertFalse(str(rep["engine_root"]).startswith("ERROR"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
