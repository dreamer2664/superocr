#!/usr/bin/env python3
"""qcaptcha solver — capture -> read -> clean -> deliver, with an honest log.

One read cycle (read_once):
  1. capture the calibrated captcha region from the LIVE screen
  2. read it through the shipping engine (lex route); one 2x-upscale retry
     if the read comes back empty
  3. clean (strip / collapse whitespace) — non-empty reads are delivered as-is
  4. deliver into the calibrated text box (focus click + paste/type)
  5. append a row to the history CSV and emit an event

The loop (run_loop) repeats with the configured interval until stopped.
Everything is injectable: tests pass fake capture/deliver functions.
"""
from __future__ import annotations

import csv
import platform
import random
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import hashlib

from . import capture as capture_mod
from . import injection as injection_mod

HISTORY_COLUMNS = ["ts_utc", "text", "raw_conf", "ms", "delivered", "mode",
                   "backend", "detect", "seconds", "error",
                   "captcha_region", "target_region"]


def history_path(config_path: Path | None = None) -> Path:
    base = Path.home()
    if platform.system() == "Windows" and __import__("os").environ.get("APPDATA"):
        base = Path(__import__("os").environ["APPDATA"])
    return base / ".qcaptcha-history.csv"


def clean_text(text: str) -> str:
    """Captcha text: strip the edges, collapse internal runs of whitespace."""
    return re.sub(r"\s+", " ", str(text)).strip()


class Solver:
    def __init__(self, cfg: dict, reader, *,
                 capture_fn=None, deliver_fn=None,
                 history: Path | None = None, log_fn=None):
        """`reader` is anything exposing read_with_retry(image, retry_upscale=…):
        qcaptcha.readers.LocalReader / GeminiReader, or a test double."""
        self.cfg = cfg
        self.reader = reader
        self.capture = capture_fn or capture_mod.grab
        self.deliver_fn = deliver_fn or injection_mod.deliver
        self.history = history or history_path()
        self.log = log_fn or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._last_text: str | None = None
        self._delivered_hash: str | None = None   # captcha pixels we already answered
        self._delivered_text: str | None = None
        self._last_solve_ts: float = 0.0
        self._stop = threading.Event()

    # ------------------------------------------------------------------ one read
    def read_once(self, *, deliver: bool = True) -> dict:
        t0 = time.perf_counter()
        row = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "text": "", "raw_conf": 0.0, "ms": 0, "delivered": False,
               "mode": "", "error": None,
               "captcha_region": self.cfg.get("captcha_region"),
               "target_region": self.cfg.get("target_region")}
        try:
            if self._auto_available():
                self._read_auto(row, deliver=deliver)
            else:
                self._read_manual(row, deliver=deliver)
        except capture_mod.CaptureError as e:
            row["error"] = f"capture: {e}"
        except injection_mod.InjectError as e:
            row["error"] = f"inject: {e}"
        except Exception as e:  # engine/other — keep the app alive, log honestly
            row["error"] = f"{type(e).__name__}: {e}"
        finally:
            row["ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            self._log_row(row)
        return row

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _crop_hash(img) -> str:
        return hashlib.sha1(img.tobytes()).hexdigest()

    def _deliver(self, row: dict, text: str, target_region, crop) -> None:
        info = self.deliver_fn(
            text, target_region,
            mode=self.cfg.get("paste_mode", "paste"),
            restore_clipboard=self.cfg.get("restore_clipboard", True),
            pause_before_paste_ms=self.cfg.get("pause_before_paste_ms", 120),
        )
        row.update(delivered=bool(info.get("delivered")),
                   mode=str(info.get("mode_used") or ""))
        if row["delivered"]:
            self._last_text = text
            if crop is not None:
                self._delivered_hash = self._crop_hash(crop)
                self._delivered_text = text
        else:
            row["error"] = f"not typed: {info.get('error') or 'delivery did not report success'}"

    # ---------------------------------------------------- auto path (per captcha)
    def _auto_available(self) -> bool:
        """Gemini can find the boxes itself — then the manual calibration is a
        hint, not a prerequisite, and every captcha is solved with fresh boxes."""
        return bool(self.cfg.get("auto_detect", True)) and hasattr(self.reader, "read_page")

    def _read_auto(self, row: dict, *, deliver: bool) -> None:
        c_reg = self.cfg.get("captcha_region")
        t_reg = self.cfg.get("target_region")
        row["detect"] = "auto"
        # Cheap skip: same captcha pixels as the one we already answered and it
        # has not been on screen long enough to force a re-check -> no API call.
        force = float(self.cfg.get("force_resolve_after_s", 10.0) or 0.0)
        if (not self.cfg.get("always_detect", False) and c_reg
                and self._delivered_hash is not None
                and (time.time() - self._last_solve_ts) < force):
            try:
                if self._crop_hash(self.capture(c_reg)) == self._delivered_hash:
                    row["detect"] = "auto-skip"
                    row["error"] = "duplicate (same captcha still on screen)"
                    return
            except capture_mod.CaptureError:
                raise
            except Exception:
                pass
        shot = capture_mod.grab_full()
        hint = None
        if c_reg:
            hint = {"captcha": [int(v) for v in c_reg],
                    "input": [int(v) for v in t_reg] if t_reg else None}
        res = self.reader.read_page(shot, hint=hint)
        cap_box, inp_box = res.get("captcha_box"), res.get("input_box")
        text = clean_text(res.get("text", ""))
        crop = None
        if cap_box:
            x, y, w, h = [int(v) for v in cap_box]
            crop = shot.crop((x, y, x + w, y + h))
        self._last_solve_ts = time.time()
        row.update(text=text, raw_conf=res.get("conf"), backend=res.get("backend", ""),
                   seconds=res.get("seconds"),
                   captcha_region=cap_box or c_reg, target_region=inp_box or t_reg)
        if cap_box:
            self.cfg["captcha_region"] = [int(v) for v in cap_box]
        if inp_box:
            self.cfg["target_region"] = [int(v) for v in inp_box]
        if not text:
            # Fallback: the one-call solve gave no text — re-read the captcha crop
            # with the classic two-step path (already live-verified, no extra
            # request unless the combined reply came back empty).
            try:
                if crop is None and c_reg:
                    x, y, w, h = [int(v) for v in c_reg]
                    crop = shot.crop((x, y, x + w, y + h))
                if crop is not None:
                    res2 = self.reader.read_with_retry(
                        crop, retry_upscale=self.cfg.get("retry_upscale", True))
                    text = clean_text(res2.get("text", ""))
                    if text:
                        row.update(text=text, raw_conf=res2.get("conf"),
                                   detect="auto+re-read", seconds=res2.get("seconds"))
            except Exception as e:
                row["error"] = f"re-read failed: {type(e).__name__}"
        if not text:
            row["error"] = "empty read (one-call solve + re-read)"
            return
        if (crop is not None and self._delivered_hash is not None
                and self._crop_hash(crop) == self._delivered_hash
                and text == self._delivered_text):
            # identical pixels + identical text = the captcha we already answered
            row["detect"] = "auto-repeat"
            row["error"] = "duplicate (same captcha already answered)"
            return
        target = inp_box or t_reg
        if deliver:
            if not target:
                row["error"] = "text box not found on screen (read-only)"
                return
            self._deliver(row, text, target, crop)

    # ----------------------------------------------------------------- manual path
    def _read_manual(self, row: dict, *, deliver: bool) -> None:
        c_reg = self.cfg.get("captcha_region")
        t_reg = self.cfg.get("target_region")
        row["detect"] = "manual"
        if not c_reg:
            row["error"] = "captcha region not calibrated"
            return
        img = self.capture(c_reg)
        res = self.reader.read_with_retry(img, retry_upscale=self.cfg.get("retry_upscale", True))
        text = clean_text(res["text"])
        row.update(text=text, raw_conf=res.get("conf"),
                   backend=res.get("backend", ""), seconds=res.get("seconds"))
        if not text:
            row["error"] = "empty read (two attempts)"
            return
        if self.cfg.get("skip_duplicates") and text == self._last_text:
            row["error"] = "duplicate (skipped by config)"
            return
        if deliver:
            if not t_reg:
                row["error"] = "target region not calibrated (read-only)"
                return
            self._deliver(row, text, t_reg, img)

    # ------------------------------------------------------------------ loop
    def run_loop(self, on_event, interval_ms: int | None = None,
                 max_reads: int | None = None,
                 max_consecutive_capture_errors: int = 5) -> None:
        """Poll until stop() (or max_reads for tests). on_event(row) per cycle.

        Gives up (with one final {'_stopped': True} event) after N consecutive
        CAPTURE errors — that state means the calibration or the permissions are
        broken, and spamming the log every interval helps nobody.
        """
        n = 0
        consec = 0
        while not self._stop.is_set():
            with self._lock:
                row = self.read_once()
            n += 1
            if str(row.get("error") or "").startswith("capture:"):
                consec += 1
            else:
                consec = 0
            try:
                on_event(row)
            except Exception:
                pass
            if max_consecutive_capture_errors and consec >= max_consecutive_capture_errors:
                try:
                    on_event({"_stopped": True, "text": "", "delivered": False,
                              "ms": 0, "raw_conf": 0.0,
                              "error": f"stopped after {consec} capture errors — "
                                       f"re-calibrate (F11) or check capture permissions"})
                except Exception:
                    pass
                return
            if max_reads is not None and n >= max_reads:
                return
            base = (interval_ms if interval_ms is not None
                    else int(self.cfg.get("interval_ms", 1500))) / 1000.0
            jitter = base * 0.15
            if self._stop.wait(max(0.05, base + random.uniform(-jitter, jitter))):
                return

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ log
    def _log_row(self, row: dict) -> None:
        try:
            self.history.parent.mkdir(parents=True, exist_ok=True)
            new = not self.history.exists()
            with self.history.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS)
                if new:
                    w.writeheader()
                w.writerow({k: row.get(k) for k in HISTORY_COLUMNS})
        except Exception as e:
            self.log(f"history log failed: {e}")
