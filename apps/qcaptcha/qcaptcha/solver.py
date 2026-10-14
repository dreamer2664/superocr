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

from . import capture as capture_mod
from . import injection as injection_mod

HISTORY_COLUMNS = ["ts_utc", "text", "raw_conf", "ms", "delivered", "mode",
                   "error", "captcha_region", "target_region"]


def history_path(config_path: Path | None = None) -> Path:
    base = Path.home()
    if platform.system() == "Windows" and __import__("os").environ.get("APPDATA"):
        base = Path(__import__("os").environ["APPDATA"])
    return base / ".qcaptcha-history.csv"


def clean_text(text: str) -> str:
    """Captcha text: strip the edges, collapse internal runs of whitespace."""
    return re.sub(r"\s+", " ", str(text)).strip()


class Solver:
    def __init__(self, cfg: dict, engine, *,
                 capture_fn=None, deliver_fn=None,
                 history: Path | None = None, log_fn=None):
        self.cfg = cfg
        self.engine = engine
        self.capture = capture_fn or capture_mod.grab
        self.deliver_fn = deliver_fn or injection_mod.deliver
        self.history = history or history_path()
        self.log = log_fn or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._last_text: str | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ one read
    def read_once(self, *, deliver: bool = True) -> dict:
        t0 = time.perf_counter()
        row = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "text": "", "raw_conf": 0.0, "ms": 0, "delivered": False,
               "mode": "", "error": None,
               "captcha_region": self.cfg.get("captcha_region"),
               "target_region": self.cfg.get("target_region")}
        c_reg = self.cfg.get("captcha_region")
        t_reg = self.cfg.get("target_region")
        if not c_reg:
            row["error"] = "captcha region not calibrated"
            self._log_row(row)
            return row
        try:
            img = self.capture(c_reg)
            res = self.engine.read_with_retry(img, retry_upscale=self.cfg.get("retry_upscale", True))
            text = clean_text(res["text"])
            row.update(text=text, raw_conf=res["conf"])
            if not text:
                row["error"] = "empty read (two attempts)"
                self._log_row(row)
                return row
            if self.cfg.get("skip_duplicates") and text == self._last_text:
                row["error"] = "duplicate (skipped by config)"
                self._log_row(row)
                return row
            self._last_text = text
            if deliver:
                if not t_reg:
                    row["error"] = "target region not calibrated (read-only)"
                    self._log_row(row)
                    return row
                info = self.deliver_fn(
                    text, t_reg,
                    mode=self.cfg.get("paste_mode", "paste"),
                    restore_clipboard=self.cfg.get("restore_clipboard", True),
                    pause_before_paste_ms=self.cfg.get("pause_before_paste_ms", 120),
                )
                row.update(delivered=bool(info.get("delivered")),
                           mode=str(info.get("mode_used") or ""))
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

    # ------------------------------------------------------------------ loop
    def run_loop(self, on_event, interval_ms: int | None = None,
                 max_reads: int | None = None) -> None:
        """Poll until stop() (or max_reads for tests). on_event(row) per cycle."""
        n = 0
        while not self._stop.is_set():
            with self._lock:
                row = self.read_once()
            n += 1
            try:
                on_event(row)
            except Exception:
                pass
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
