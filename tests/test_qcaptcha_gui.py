#!/usr/bin/env python3
"""qcaptcha GUI end-to-end — needs a display. Headless runner:

    xvfb-run -a -s "-screen 0 1280x800x24" python3 tests/test_qcaptcha_gui.py

What it proves, for real (no fakes):
  * a captcha image is ON the screen; the app captures that region from the
    live X display (Pillow X11), reads it via the shipping engine, and the read
    matches an independent direct engine read of the same image;
  * the answer is DELIVERED into a different window's text widget through the
    real injection path (xdotool click + clipboard via xclip + Ctrl+V);
  * calibration overlay: simulated drag -> exact region in screen pixels;
  * the CLI `--once --no-paste` path returns the same read as JSON.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps" / "qcaptcha"
sys.path.insert(0, str(APP))

HAVE_DISPLAY = bool(os.environ.get("DISPLAY")) and os.environ.get("QCAPTCHA_GUI_SKIP") != "1"


@unittest.skipUnless(HAVE_DISPLAY, "no DISPLAY (run under xvfb-run)")
class TestAutoCalibration(unittest.TestCase):
    """Gemini auto-calibration overlay: accept / redraw / cancel — no network."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.root = tk.Tk()
        cls.root.geometry("1280x800+0+0")
        cls.pump(0.3)

    @classmethod
    def pump(cls, seconds=0.1):
        end = time.time() + seconds
        while time.time() < end:
            cls.root.update()
            time.sleep(0.02)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def _show(self, proposed):
        from qcaptcha.overlay import AutoCalibrationOverlay
        from qcaptcha import capture as capture_mod
        shot = capture_mod.grab_full()
        got = {}
        ov = AutoCalibrationOverlay(self.root, lambda r: got.update(result=r), shot,
                                    proposed, "test prompt")
        self.pump(0.25)
        return ov, got

    def test_enter_accepts_suggestions(self):
        proposed = {"captcha": [40, 60, 520, 150], "input": [40, 300, 520, 46]}
        ov, got = self._show(proposed)
        ov.win.event_generate("<Return>")
        self.pump(0.2)
        self.assertEqual(got["result"], {"captcha": [40, 60, 520, 150],
                                         "input": [40, 300, 520, 46]})

    def test_drag_overrides_captcha_then_input(self):
        ov, got = self._show({"captcha": None, "input": None})
        ov.canvas.event_generate("<Button-1>", x=100, y=100)
        ov.canvas.event_generate("<B1-Motion>", x=400, y=250)
        ov.canvas.event_generate("<ButtonRelease-1>", x=400, y=250)
        self.pump(0.1)
        ov.canvas.event_generate("<Button-1>", x=100, y=400)
        ov.canvas.event_generate("<B1-Motion>", x=700, y=450)
        ov.canvas.event_generate("<ButtonRelease-1>", x=700, y=450)
        self.pump(0.1)
        ov.win.event_generate("<Return>")
        self.pump(0.2)
        r = got["result"]
        self.assertEqual(r["captcha"], [100, 100, 300, 150])
        self.assertEqual(r["input"], [100, 400, 600, 50])

    def test_esc_cancels(self):
        ov, got = self._show({"captcha": [1, 2, 300, 100], "input": None})
        ov.win.event_generate("<Escape>")
        self.pump(0.2)
        self.assertIsNone(got["result"])


class TestGuiEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        from PIL import ImageTk

        from qcaptcha import engine as engine_mod

        cls.tmp = tempfile.TemporaryDirectory()
        cls.engine = engine_mod.ReaderEngine(ROOT)
        cls.img, cls.label = cls.engine.generate_sample(777001, "easy")
        cls.expected, _ = cls.engine.read(cls.img)

        cls.root = tk.Tk()
        cls.root.geometry("1280x800+0+0")
        cls.root.update_idletasks()
        cls.pump(0.3)

        # captcha window — WM-free, exact placement (x,y = the region we calibrate)
        cls.cx, cls.cy = 40, 60
        cwin = tk.Toplevel(cls.root)
        cwin.overrideredirect(True)
        cwin.geometry(f"{cls.img.width}x{cls.img.height}+{cls.cx}+{cls.cy}")
        cls.photo = ImageTk.PhotoImage(cls.img)
        cl = tk.Label(cwin, image=cls.photo, borderwidth=0)
        cl.pack()
        cls.cwin = cwin

        # target window — a text box in a DIFFERENT window
        cls.tx, cls.ty, cls.tw, cls.th = 500, 300, 360, 140
        twin = tk.Toplevel(cls.root)
        twin.overrideredirect(True)
        twin.geometry(f"{cls.tw}x{cls.th}+{cls.tx}+{cls.ty}")
        cls.text = tk.Text(twin, width=40, height=6, font=("TkFixedFont", 11))
        cls.text.pack(fill="both", expand=True)
        cls.twin = twin
        cls.pump(0.4)

    @classmethod
    def pump(cls, seconds=0.1):
        end = time.time() + seconds
        while time.time() < end:
            try:
                cls.root.update()
            except Exception:
                break
            time.sleep(0.02)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        from qcaptcha import config as config_mod
        from qcaptcha.overlay import SolverApp
        from qcaptcha.solver import Solver

        self.cfg_path = Path(self.tmp.name) / "cfg.json"
        cfg = config_mod.validate({
            "captcha_region": [self.cx, self.cy, self.img.width, self.img.height],
            "target_region": [self.tx, self.ty, self.tw, self.th],
            "pause_before_paste_ms": 250,
            # keep the always-on-top panel clear of both regions (it would be
            # captured/photographed otherwise) — same advice the README gives users
            "panel_pos": [930, 20],
        })
        self.solver = Solver(cfg, self.engine, history=Path(self.tmp.name) / "h.csv")
        self.app = SolverApp(cfg, self.engine, root=self.root,
                             config_path=self.cfg_path, solver=self.solver)

    def tearDown(self):
        try:
            self.app._stop_loop()
            self.app.panel.destroy()
        except Exception:
            pass
        self.text.delete("1.0", "end")

    def test_full_chain_screen_to_text_box(self):
        self.assertTrue(self.expected, "engine must read the sample for the test to be meaningful")
        row = self.app._read_once_safe(deliver=True)
        self.assertIsNone(row.get("error"), msg=str(row.get("error")))
        self.assertEqual(row["text"], self.expected)
        self.assertTrue(row["delivered"], "delivery must have happened")

        # the answer is IN the other window's text box (real xdotool + Ctrl+V)
        deadline = time.time() + 3.0
        got = ""
        while time.time() < deadline:
            self.pump(0.15)
            got = self.text.get("1.0", "end").strip()
            if got:
                break
        self.assertEqual(got, self.expected,
                         "text box must contain the read captcha (got %r)" % got)

    def test_calibration_overlay_drag_defines_exact_region(self):
        from qcaptcha.overlay import CalibrationOverlay
        got = {}
        ov = CalibrationOverlay(self.root, lambda r: got.update(region=r),
                                "test prompt", "#2ecc71", default_size=(160, 60))
        self.pump(0.2)
        # canvas is 1:1 with the frozen screen (1280x800 under xvfb) — drag a box
        ov.canvas.event_generate("<Button-1>", x=100, y=100)
        ov.canvas.event_generate("<B1-Motion>", x=300, y=170)
        ov.canvas.event_generate("<ButtonRelease-1>", x=300, y=170)
        self.pump(0.1)
        ov.win.event_generate("<Return>")
        self.pump(0.2)
        self.assertIn("region", got)
        self.assertEqual(got["region"], [100, 100, 200, 70])

    def test_single_click_default_box(self):
        from qcaptcha.overlay import CalibrationOverlay
        got = {}
        ov = CalibrationOverlay(self.root, lambda r: got.update(region=r),
                                "test prompt", "#3aa0ff", default_size=(120, 40))
        self.pump(0.2)
        ov.canvas.event_generate("<Button-1>", x=400, y=400)
        ov.canvas.event_generate("<ButtonRelease-1>", x=402, y=401)
        self.pump(0.1)
        ov.win.event_generate("<Return>")
        self.pump(0.2)
        r = got["region"]
        self.assertEqual(r[2:], [120, 40])
        self.assertAlmostEqual(r[0] + r[2] / 2, 400, delta=3)
        self.assertAlmostEqual(r[1] + r[3] / 2, 400, delta=3)

    def test_cli_once_matches_app_read(self):
        from qcaptcha import config as config_mod
        config_mod.save({
            "captcha_region": [self.cx, self.cy, self.img.width, self.img.height],
            "target_region": [self.tx, self.ty, self.tw, self.th],
        }, self.cfg_path)
        p = subprocess.run(
            [sys.executable, str(APP / "launcher.py"), "--once", "--no-paste",
             "--config", str(self.cfg_path), "--engine", str(ROOT)],
            capture_output=True, text=True, timeout=180, env={**os.environ})
        self.assertEqual(p.returncode, 0, msg=p.stderr[-400:])
        row = json.loads(p.stdout)
        self.assertIsNone(row.get("error"))
        self.assertEqual(row["text"], self.expected)


@unittest.skipUnless(HAVE_DISPLAY and os.environ.get("QCAPTCHA_LIVE") == "1"
                     and (Path.home() / ".private" / "gemini-keys.json").is_file(),
                     "live auto-calibration: needs DISPLAY + keys + QCAPTCHA_LIVE=1")
class TestLiveAutoCalibration(unittest.TestCase):
    """Synthetic page on Xvfb -> real screenshot -> real Gemini detection -> IoU."""

    def test_detect_regions_end_to_end(self):
        import tkinter as tk
        import time as _t
        from PIL import ImageTk
        from qcaptcha import capture as capture_mod
        from qcaptcha import gemini as G
        sys.path.insert(0, str(ROOT))
        import generator as gen_mod

        CAP, CAP_SZ = (40, 60), (520, 150)
        INP, INP_SZ = (40, 300), (520, 46)
        img, _ = gen_mod.generate_one("easy", 5555, 0)
        img = img.resize(CAP_SZ)

        root = tk.Tk(); root.geometry("1280x800+0+0"); root.configure(bg="#f4f4f4")
        tk.Label(root, image=ImageTk.PhotoImage(img), borderwidth=0).place(x=CAP[0], y=CAP[1])
        tk.Label(root, text="Type the letters shown above:", bg="#f4f4f4",
                 font=("TkDefaultFont", 12)).place(x=INP[0], y=INP[1]-28)
        tk.Text(root, width=60, height=2, font=("TkDefaultFont", 12), relief="solid",
                borderwidth=2, bg="white").place(x=INP[0], y=INP[1],
                                                 width=INP_SZ[0], height=INP_SZ[1])
        end = _t.time() + 0.8
        while _t.time() < end:
            root.update(); _t.sleep(0.02)

        shot = capture_mod.grab_full()
        client = G.GeminiClient(keys_file=str(Path.home() / ".private" / "gemini-keys.json"))
        boxes = G.detect_regions(client, shot)
        root.destroy()

        def iou(a, b):
            ax, ay, aw, ah = a; bx, by, bw, bh = b
            ix = max(0, min(ax+aw, bx+bw) - max(ax, bx))
            iy = max(0, min(ay+ah, by+bh) - max(ay, by))
            inter = ix*iy; union = aw*ah + bw*bh - inter
            return inter/union if union else 0.0

        self.assertIsNotNone(boxes["captcha"], f"captcha not found: {boxes}")
        self.assertIsNotNone(boxes["input"], f"input not found: {boxes}")
        self.assertGreater(iou(boxes["captcha"], (*CAP, *CAP_SZ)), 0.55)
        self.assertGreater(iou(boxes["input"], (*INP, *INP_SZ)), 0.40)


if __name__ == "__main__":
    # the CLI test needs the config on disk before the subprocess starts
    if HAVE_DISPLAY and "TestGuiEndToEnd" in globals():
        unittest.main(verbosity=2)
    else:
        print("no DISPLAY — skipping GUI tests (run under xvfb-run)")
