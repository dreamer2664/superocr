#!/usr/bin/env python3
"""qcaptcha overlay — the tkinter UI.

Two windows:
  * PANEL   — a small always-on-top console: status, the last read, buttons
              (Calibrate, Arm/Disarm, Read now, Save, Quit) and a short log.
  * CALIBRATOR — a fullscreen window that shows a FROZEN screenshot at
              calibration time, dimmed, on top of everything. You drag a
              rectangle (or just click for a default-size box) over the captcha
              image, then over the text box. What you mark is what the app
              reads and where it types — regions are stored in screen pixels.

Hotkeys: F9 arm/disarm · F10 read now once · F11 re-run calibration.

While ARMED the app shows no fullscreen overlay (it would block the page you
are solving); it just polls. The panel is the only window on screen.
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

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

        img = capture_mod.grab_full()
        self.img = img
        self.win = tk.Toplevel(root)
        self.win.title("qcaptcha calibration")
        # WM-free fullscreen: explicit size + no decorations. Works identically
        # on bare X (Xvfb, tiling WMs) and on Windows/macOS where a WM exists.
        try:
            self.win.overrideredirect(True)
        except tk.TclError:
            pass
        self.win.geometry(f"{img.width}x{img.height}+0+0")
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.win.configure(bg="black", cursor="crosshair")
        self.canvas = tk.Canvas(self.win, highlightthickness=0, borderwidth=0, bg="black")
        self.canvas.pack(fill="both", expand=True)
        self.win.update_idletasks()
        self.cw = max(1, self.canvas.winfo_width())
        self.ch = max(1, self.canvas.winfo_height())
        # scale frozen image to canvas (handles DPI scaling distortions)
        self.photo = ImageTk.PhotoImage(img.resize((self.cw, self.ch), Image.LANCZOS))
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        # dim it so overlay markers pop
        self.canvas.create_rectangle(0, 0, self.cw, self.ch, fill="#000000", stipple="gray50",
                                     outline="")
        self.canvas.create_text(20, 18, anchor="nw", fill=FG, font=("TkDefaultFont", 14, "bold"),
                                text=prompt)
        self.canvas.create_text(20, 44, anchor="nw", fill=DIM, font=("TkDefaultFont", 10),
                                text="drag a box, or single-click for a default-size box    "
                                     "·  Enter = confirm  ·  Esc = cancel")
        if existing:
            self._draw_region(existing, DIM, "current")
        self._rect_id = None
        self._start = None
        self._region = None
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Return>", lambda e: self._confirm())
        self.win.bind("<Escape>", lambda e: self._cancel())
        self.win.focus_force()

    # canvas <-> image coordinate mapping (identical scale both axes)
    def _to_canvas(self, region):
        x, y, w, h = region
        sx, sy = self.cw / self.img.width, self.ch / self.img.height
        return x * sx, y * sy, (x + w) * sx, (y + h) * sy

    def _to_image(self, cx0, cy0, cx1, cy1):
        sx, sy = self.img.width / self.cw, self.img.height / self.ch
        x0, x1 = sorted((cx0, cx1))
        y0, y1 = sorted((cy0, cy1))
        return [int(round(x0 * sx)), int(round(y0 * sy)),
                int(round((x1 - x0) * sx)), int(round((y1 - y0) * sy))]

    def _draw_region(self, region, color, label):
        x0, y0, x1, y1 = self._to_canvas(region)
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
        self.canvas.create_text(x0 + 4, max(10, y0 - 10), anchor="w", fill=color,
                                text=label, font=("TkDefaultFont", 9, "bold"))

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
            cx0, cy0 = x0 - self.default_w // 2, y0 - self.default_h // 2
            cx1, cy1 = cx0 + self.default_w, cy0 + self.default_h
        else:
            cx0, cy0, cx1, cy1 = x0, y0, e.x, e.y
        reg = self._to_image(cx0, cy0, cx1, cy1)
        if reg[2] < 8 or reg[3] < 8:
            reg = self._to_image(cx0, cy0, cx0 + 24, cy0 + 24)
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

    # ------------------------------------------------------------------ arm / read
    def toggle_arm(self):
        if self.armed:
            self._stop_loop()
        else:
            if not (self.cfg.get("captcha_region") and self.cfg.get("target_region")):
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
        self.btn_arm.configure(text="Arm ▶", bg=GREEN)
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
        err = row.get("error")
        if err:
            self.last_text.configure(text="⚠", fg=RED)
            self.detail.configure(text=str(err)[:120], fg=RED)
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
