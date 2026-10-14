#!/usr/bin/env python3
"""qcaptcha overlay — the tkinter UI (v1.0.1).

Two windows:
  * PANEL   — a small always-on-top console: status, the last read, buttons
              (Calibrate, Arm/Disarm, Read now, Save, Quit) and a short log.
  * CALIBRATOR — a fullscreen window that shows a FROZEN screenshot taken at
              calibration time, dimmed, on top of everything. You drag a
              rectangle (or single-click for a default-size box) over the
              captcha image, then over the text box. What you mark is what the
              app reads and where it types — regions are stored in screen pixels.

v1.0.1 hardening (fixes the "ARM … ERR capture: Image size … exceeds" report):
  * the frozen screenshot is only drawn once the window is really mapped —
    a not-yet-mapped canvas (winfo_width() == 1) used to produce garbage
    scaled regions;
  * canvas→screen mapping is a pure, clamped function (map_canvas_to_image)
    with a 1:1 fallback: a region can never exceed the frozen image;
  * corrupt saved calibrations are dropped on load and again at Arm time
    (the wizard re-opens instead of spamming capture errors);
  * the arm loop stops after 5 consecutive capture errors with a clear note;
  * an all-black freeze gets an explicit warning line (permission problem).

Hotkeys: F9 arm/disarm · F10 read now once · F11 re-run calibration.
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageStat, ImageTk

from . import capture as capture_mod
from . import config as config_mod
from .solver import Solver

PANEL_BG = "#101418"
FG = "#e8eef4"
DIM = "#8aa0b4"
GREEN = "#2ecc71"
RED = "#e74c3c"
AMBER = "#f1c40f"
ACCENT = "#3aa0ff"

MAX_REGION_SIDE = 20000          # px; anything bigger is not a real screen box
MAX_REGION_PIXELS = 60_000_000   # 60 MP; generous for multi-monitor boxes


def map_canvas_to_image(cx0, cy0, cx1, cy1, cw, ch, iw, ih, min_side=8):
    """Pure mapping: canvas drag coords -> region [x, y, w, h] in image pixels.

    Robust on purpose:
      * if the canvas is not (yet) a real size (cw/ch <= 2), assumes 1:1;
      * the drawn box is clamped to the canvas first, the result to the image;
      * output is always inside the image and at least `min_side` px per side.
    """
    usable = bool(cw and ch and cw > 2 and ch > 2)
    sx = (iw / cw) if usable else 1.0
    sy = (ih / ch) if usable else 1.0
    x0, x1 = sorted((float(cx0), float(cx1)))
    y0, y1 = sorted((float(cy0), float(cy1)))
    mx, my = (cw, ch) if usable else (iw, ih)
    x0, x1 = max(0.0, min(x0, mx)), max(0.0, min(x1, mx))
    y0, y1 = max(0.0, min(y0, my)), max(0.0, min(y1, my))
    rx0 = max(0, min(int(round(x0 * sx)), iw))
    ry0 = max(0, min(int(round(y0 * sy)), ih))
    rx1 = max(0, min(int(round(x1 * sx)), iw))
    ry1 = max(0, min(int(round(y1 * sy)), ih))
    w = max(min_side, rx1 - rx0)
    h = max(min_side, ry1 - ry0)
    w = min(w, iw)
    h = min(h, ih)
    rx0 = min(rx0, iw - w)
    ry0 = min(ry0, ih - h)
    rx0 = max(0, rx0)
    ry0 = max(0, ry0)
    return [rx0, ry0, w, h]


class CalibrationOverlay:
    """Fullscreen frozen-screenshot calibration. One region per show call."""

    def __init__(self, root: tk.Tk, on_done, prompt: str, color: str,
                 default_size=(160, 60), existing=None):
        self.root = root
        self.on_done = on_done          # callable(region | None)
        self.done = False
        self.result = None
        self.color = color
        self.default_w, self.default_h = default_size
        self.prompt = prompt
        self._existing = existing
        self.cw = 0
        self.ch = 0
        self.photo = None
        self._rect_id = None
        self._start = None
        self._region = None
        self._tries = 0
        self._black = False

        self.win = tk.Toplevel(root)
        self.win.title("qcaptcha calibration")
        # WM-free fullscreen: explicit size + no decorations. Works identically
        # on bare X (Xvfb, tiling WMs) and on Windows/macOS where a WM exists.
        try:
            self.win.overrideredirect(True)
        except tk.TclError:
            pass
        self.img = capture_mod.grab_full()
        self.win.geometry(f"{self.img.width}x{self.img.height}+0+0")
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.configure(bg="black", cursor="crosshair")

        self.canvas = tk.Canvas(self.win, highlightthickness=0, borderwidth=0, bg="black")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Return>", lambda e: self._confirm())
        self.win.bind("<Escape>", lambda e: self._cancel())
        self.win.focus_force()
        # Draw only when the window is actually mapped — before that,
        # winfo_width() lies (returns 1) and any scale factor computed from it
        # is garbage. See module docstring.
        self._detect_black()
        self.win.after(40, self._prepare)

    # ------------------------------------------------------------------ prep
    def _detect_black(self) -> None:
        try:
            small = self.img.convert("L").resize((32, 32))
            self._black = ImageStat.Stat(small).mean[0] < 3.0
        except Exception:
            self._black = False

    def _prepare(self):
        if self.done:
            return
        try:
            self.win.update_idletasks()
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
        except tk.TclError:
            return
        if cw <= 2 or ch <= 2:
            self._tries += 1
            if self._tries < 12:                 # ~1 s of retries
                self.win.after(80, self._prepare)
                return
            cw, ch = self.img.width, self.img.height   # give up gracefully: 1:1
        self.cw, self.ch = cw, ch
        try:
            self.photo = ImageTk.PhotoImage(self.img.resize((cw, ch), Image.LANCZOS))
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
            # dim it so overlay markers pop
            self.canvas.create_rectangle(0, 0, cw, ch, fill="#000000",
                                         stipple="gray50", outline="")
            self.canvas.create_text(20, 18, anchor="nw", fill=FG,
                                    font=("TkDefaultFont", 14, "bold"), text=self.prompt)
            self.canvas.create_text(20, 44, anchor="nw", fill=DIM,
                                    font=("TkDefaultFont", 10),
                                    text="drag a box, or single-click for a default-size box    "
                                         "·  Enter = confirm  ·  Esc = cancel")
            if self._black:
                self.canvas.create_text(
                    20, 72, anchor="nw", fill=AMBER, font=("TkDefaultFont", 11, "bold"),
                    text="⚠ the frozen picture is black — screen capture is not working "
                         "(macOS: grant Screen Recording; Linux: use an X11 session). "
                         "Esc and fix that first.")
            if self._existing:
                self._draw_region(self._existing, DIM, "current")
        except tk.TclError:
            pass

    # canvas <-> image coordinate mapping (identical scale both axes)
    def _to_canvas(self, region):
        x, y, w, h = region
        sx, sy = self.cw / self.img.width, self.ch / self.img.height
        return x * sx, y * sy, (x + w) * sx, (y + h) * sy

    def _to_image(self, cx0, cy0, cx1, cy1):
        return map_canvas_to_image(cx0, cy0, cx1, cy1,
                                   self.cw, self.ch, self.img.width, self.img.height)

    def _draw_region(self, region, color, label):
        if self.cw <= 2 or self.ch <= 2:
            return
        x0, y0, x1, y1 = self._to_canvas(region)
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
        self.canvas.create_text(x0 + 4, max(10, y0 - 10), anchor="w", fill=color,
                                text=label, font=("TkDefaultFont", 9, "bold"))

    # ------------------------------------------------------------------ input
    def _press(self, e):
        self._start = (e.x, e.y)
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        self._rect_id = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                     outline=self.color, width=2, dash=(4, 2))

    def _drag(self, e):
        if not self._start or not self._rect_id:
            return
        x0, y0 = self._start
        self.canvas.coords(self._rect_id, x0, y0, e.x, e.y)

    def _release(self, e):
        if not self._start:
            return
        x0, y0 = self._start
        if abs(e.x - x0) < 4 and abs(e.y - y0) < 4:  # a plain click: default box centered
            cx0, cy0 = x0 - self.default_w / 2, y0 - self.default_h / 2
            cx1, cy1 = cx0 + self.default_w, cy0 + self.default_h
        else:
            cx0, cy0, cx1, cy1 = x0, y0, e.x, e.y
        reg = self._to_image(cx0, cy0, cx1, cy1)
        self._region = reg
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        self._rect_id = None
        self._draw_region(reg, self.color, f"selected {reg[2]}×{reg[3]}")

    def _confirm(self):
        if self._region:
            self._finish(self._region)

    def _cancel(self):
        self._finish(None)

    def _finish(self, region):
        if self.done:
            return
        self.done = True
        try:
            self.win.destroy()
        finally:
            self.on_done(region)


class SolverApp:
    def __init__(self, cfg: dict, engine, *, root: tk.Tk | None = None,
                 config_path: Path | None = None, solver: Solver | None = None):
        self.cfg = cfg
        self.config_path = Path(config_path) if config_path else config_mod.default_config_path()
        self.engine = engine
        self.root = root or tk.Tk()
        self._own_root = root is None
        self.solver = solver or Solver(cfg)
        self.solver.capture = capture_mod.grab
        self.armed = False
        self._loop_thread: threading.Thread | None = None
        self._events: list[dict] = []
        self._build_panel()
        self._bind_hotkeys()
        self.root.after(120, self._pump)

    # ------------------------------------------------------------------ UI
    def _build_panel(self):
        self.panel = tk.Toplevel(self.root)
        self.panel.title("qcaptcha — superocr screen solver")
        self.panel.configure(bg=PANEL_BG)
        try:
            self.panel.attributes("-topmost", True)
        except tk.TclError:
            pass
        pos = self.cfg.get("panel_pos")
        if pos:
            self.panel.geometry(f"+{int(pos[0])}+{int(pos[1])}")

        pad = dict(padx=10, pady=2)
        tk.Label(self.panel, text="qcaptcha", bg=PANEL_BG, fg=FG,
                 font=("TkDefaultFont", 13, "bold")).grid(row=0, column=0, sticky="w", **pad)
        self.status = tk.Label(self.panel, text="idle — not calibrated", bg=PANEL_BG, fg=AMBER,
                               font=("TkDefaultFont", 10))
        self.status.grid(row=0, column=1, sticky="e", **pad)

        self.last_text = tk.Label(self.panel, text="—", bg=PANEL_BG, fg=FG,
                                  font=("TkFixedFont", 16, "bold"))
        self.last_text.grid(row=1, column=0, columnspan=2, sticky="w", **pad)
        self.detail = tk.Label(self.panel, text="", bg=PANEL_BG, fg=DIM,
                               font=("TkDefaultFont", 9))
        self.detail.grid(row=2, column=0, columnspan=2, sticky="w", **pad)

        btns = tk.Frame(self.panel, bg=PANEL_BG)
        btns.grid(row=3, column=0, columnspan=2, sticky="we", padx=8, pady=(6, 2))
        def mk(text, cmd, col):
            b = tk.Button(btns, text=text, command=cmd, bg=col, fg="#0b0e12",
                          activebackground=col, relief="flat", padx=8, pady=4)
            b.pack(side="left", padx=3)
            return b
        self.btn_cal = mk("Calibrate", self.calibrate_wizard, "#b9c6d4")
        self.btn_arm = mk("Arm ▶", self.toggle_arm, GREEN)
        mk("Read once", lambda: self.read_now(True), "#b9c6d4")
        mk("Save", self.save_cfg, "#b9c6d4")
        mk("Quit", self.quit, "#e59b9b")

        self.hist = tk.Text(self.panel, height=7, width=44, bg="#0b0e12", fg=DIM,
                            font=("TkFixedFont", 9), relief="flat", state="disabled")
        self.hist.grid(row=4, column=0, columnspan=2, sticky="we", padx=8, pady=(4, 8))
        self.panel.protocol("WM_DELETE_WINDOW", self.quit)

    def _bind_hotkeys(self):
        self.root.bind_all("<F9>", lambda e: self.toggle_arm())
        self.root.bind_all("<F10>", lambda e: self.read_now(True))
        self.root.bind_all("<F11>", lambda e: self.calibrate_wizard())

    def _log(self, line: str):
        self.hist.configure(state="normal")
        self.hist.insert("end", line + "\n")
        self.hist.see("end")
        # keep the widget small
        if int(self.hist.index("end-1c").split(".")[0]) > 60:
            self.hist.delete("1.0", "20.0")
        self.hist.configure(state="disabled")

    # ------------------------------------------------------------------ calibration
    def calibrate_wizard(self):
        self._stop_loop()
        self._calibrate("captcha_region",
                        "1/2 — drag a box over the CAPTCHA image (single-click = default box · Enter = ok)",
                        GREEN, (160, 60),
                        lambda: self._calibrate(
                            "target_region",
                            "2/2 — click the TEXT BOX you want the answer typed into",
                            ACCENT, (200, 30), self._calibrated_done))

    def _calibrate(self, key, prompt, color, dsize, then):
        def done(region):
            if region:
                self.cfg[key] = region
                self._log(f"{key}: {region}")
                self._update_status()
            then()
        try:
            CalibrationOverlay(self.root, done, prompt, color, default_size=dsize,
                               existing=self.cfg.get(key))
        except capture_mod.CaptureError as e:
            self._set_error(f"calibration needs screen capture: {e}")
            then()

    def _calibrated_done(self):
        try:
            config_mod.save(self.cfg, self.config_path)
            self._log(f"config saved → {self.config_path}")
        except Exception as e:
            self._set_error(f"could not save config: {e}")
        self._update_status()

    # test hook: set regions without the GUI overlay
    def apply_region(self, key: str, region):
        self.cfg[key] = list(region)
        self._update_status()

    # ------------------------------------------------------------------ sanity
    def _regions_ready(self) -> bool:
        """Both regions present AND not corrupt (v1.0.1: garbage regions from a
        pre-v1.0.1 calibration used to reach the capture loop and error-spam)."""
        for key in ("captcha_region", "target_region"):
            reg = self.cfg.get(key)
            if not reg:
                return False
            _x, _y, w, h = reg
            if w < 8 or h < 8:
                return False
            if w > MAX_REGION_SIDE or h > MAX_REGION_SIDE or w * h > MAX_REGION_PIXELS:
                return False
        return True

    # ------------------------------------------------------------------ arm / read
    def toggle_arm(self):
        if self.armed:
            self._stop_loop()
        else:
            if not self._regions_ready():
                self._log("calibrate first — opening the two-click wizard")
                self.calibrate_wizard()
                return
            self._start_loop()

    def _start_loop(self):
        if self.armed:
            return
        self.armed = True
        self.solver._stop.clear()
        self._loop_thread = threading.Thread(
            target=self.solver.run_loop, args=(self._events.append,), daemon=True)
        self._loop_thread.start()
        self.btn_arm.configure(text="Disarm ■", bg=RED)
        self._log("armed — polling " + str(self.cfg.get("interval_ms", 1500)) + " ms")
        self._update_status()

    def _stop_loop(self):
        if self.armed:
            self._log("disarmed")
        self.armed = False
        self.solver.stop()
        try:
            self.btn_arm.configure(text="Arm ▶", bg=GREEN)
        except tk.TclError:
            pass
        self._update_status()

    def read_now(self, deliver: bool = True):
        threading.Thread(target=lambda: self._events.append(self._read_once_safe(deliver)),
                         daemon=True).start()

    def _read_once_safe(self, deliver):
        try:
            return self.solver.read_once(deliver=deliver)
        except Exception as e:
            return {"error": str(e), "text": "", "delivered": False, "ms": 0, "raw_conf": 0}

    # ------------------------------------------------------------------ UI pump
    def _pump(self):
        while self._events:
            row = self._events.pop(0)
            self._render(row)
        try:
            self.root.after(120, self._pump)
        except tk.TclError:
            pass

    def _render(self, row: dict):
        if row.get("_stopped"):            # loop ended itself after repeated capture errors
            self.armed = False
            try:
                self.btn_arm.configure(text="Arm ▶", bg=GREEN)
            except tk.TclError:
                pass
            self.last_text.configure(text="⚠", fg=RED)
            self.detail.configure(text=str(row.get("error"))[:140], fg=RED)
            self._log("STOPPED — " + str(row.get("error"))[:80])
            self._update_status()
            return
        err = row.get("error")
        if err:
            self.last_text.configure(text="⚠", fg=RED)
            self.detail.configure(text=str(err)[:140], fg=RED)
            self._log(f"ERR {str(err)[:90]}")
            self._update_status()
            return
        self.last_text.configure(text=row.get("text") or "—", fg=FG)
        flag = "✓ pasted" if row.get("delivered") else "read (not delivered)"
        self.detail.configure(
            text=f"{flag} · conf {row.get('raw_conf')} · {row.get('ms')} ms · {row.get('mode')}",
            fg=DIM)
        self._log(f"{row.get('text')}  [{row.get('ms')} ms{' · sent' if row.get('delivered') else ''}]")
        self._update_status()

    def _panel_overlaps_captcha(self) -> bool:
        """The panel is always-on-top: if it covers the captcha region, reads
        will photograph the panel. Warn loudly instead of failing silently."""
        reg = self.cfg.get("captcha_region")
        if not reg:
            return False
        try:
            self.panel.update_idletasks()
            px, py = self.panel.winfo_x(), self.panel.winfo_y()
            pw, ph = self.panel.winfo_width(), self.panel.winfo_height()
        except tk.TclError:
            return False
        x, y, w, h = reg
        ox = max(0, min(x + w, px + pw) - max(x, px))
        oy = max(0, min(y + h, py + ph) - max(y, py))
        return (ox * oy) > 0.15 * (w * h)  # >15% of the captcha hidden

    def _update_status(self):
        if not (self.cfg.get("captcha_region") and self.cfg.get("target_region")):
            self.status.configure(text="not calibrated — press Calibrate", fg=AMBER)
        elif not self._regions_ready():
            self.status.configure(text="calibration corrupt — press Calibrate", fg=RED)
        elif self._panel_overlaps_captcha():
            self.status.configure(text="⚠ panel covers the captcha — move it", fg=RED)
        elif self.armed:
            self.status.configure(text="● ARMED", fg=GREEN)
        else:
            self.status.configure(text="calibrated · idle", fg=DIM)

    def _set_error(self, msg: str):
        self.last_text.configure(text="⚠", fg=RED)
        self.detail.configure(text=msg[:140], fg=RED)

    # ------------------------------------------------------------------ lifecycle
    def save_cfg(self):
        try:
            self.panel.update_idletasks()
            self.cfg["panel_pos"] = [self.panel.winfo_x(), self.panel.winfo_y()]
        except Exception:
            pass
        try:
            config_mod.save(self.cfg, self.config_path)
            self._log(f"config saved → {self.config_path}")
        except Exception as e:
            self._set_error(f"could not save config: {e}")

    def quit(self):
        self._stop_loop()
        self.save_cfg()
        try:
            if self._own_root:
                self.root.destroy()
            else:
                self.panel.destroy()
        except tk.TclError:
            pass

    def run(self):
        self._update_status()
        if self._own_root:
            self.root.mainloop()
