#!/usr/bin/env python3
"""qcaptcha config — regions and settings, plain JSON, atomic writes.

Default file: ~/.qcaptcha.json  (override with QCAPTCHA_CONFIG env or --config).
A region is [x, y, w, h] in screen pixels: x/y = top-left corner.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

VERSION = 1

DEFAULTS: dict = {
    "version": VERSION,
    "captcha_region": None,   # [x, y, w, h] — where the captcha image is
    "target_region": None,    # [x, y, w, h] — the text box to paste into
    "interval_ms": 1500,      # poll interval while armed
    "pause_before_paste_ms": 120,   # after focusing the text box, before typing
    "paste_mode": "paste",    # "paste" (clipboard + Ctrl/Cmd+V) or "type" (keystrokes)
    "restore_clipboard": True,
    "retry_upscale": True,    # one 2x upscale retry when the read comes back empty
    "skip_duplicates": False, # if True, do not re-paste an identical read
    "panel_pos": None,        # [x, y] remembered console position
    # --- reader backend -------------------------------------------------
    "auto_detect": True,           # Gemini finds captcha+box fresh on every solve
    "always_detect": False,        # skip the pixel-hash shortcut; ask every cycle
    "force_resolve_after_s": 10.0, # re-check the screen at least this often
    "solve_on_calibrate": True,    # after Auto (Gemini): read + type once, at once
    "type_test_text": "qcaptcha test 123",
    "reader_backend": "gemini",       # "gemini" (API) or "local" (offline reader)
    "gemini_keys_file": "~/.qcaptcha-keys.json",
    "gemini_model": "gemini-3-flash-preview",
    "gemini_models": [],              # optional fallback chain; [] = built-in chain
    "gemini_apply_lex": False,        # project Gemini text onto the 128-word vocab (off)
    "gemini_timeout_s": 45.0,
}


def default_config_path() -> Path:
    env = os.environ.get("QCAPTCHA_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".qcaptcha.json"


MAX_REGION_SIDE = 20_000          # px — keep in sync with capture.py
MAX_REGION_PIXELS = 60_000_000    # 60 MP


def _valid_region(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(v, (int, float)) for v in value)
        and 8 <= value[2] <= MAX_REGION_SIDE
        and 8 <= value[3] <= MAX_REGION_SIDE
        and value[2] * value[3] <= MAX_REGION_PIXELS
    )


def validate(cfg: dict) -> dict:
    """Return cfg with only known keys, validated; raises ValueError on bad values."""
    out = dict(DEFAULTS)
    unknown = set(cfg) - set(DEFAULTS)
    if unknown:
        # forward-compatible: keep unknown keys (future versions), don't crash
        pass
    out.update(cfg)
    for key in ("captcha_region", "target_region"):
        v = out.get(key)
        if v is not None and not _valid_region(v):
            raise ValueError(f"{key} must be [x, y, w, h] with w,h >= 8; got {v!r}")
        if v is not None:
            out[key] = [int(round(float(c))) for c in v]
    if out.get("panel_pos") is not None:
        pp = out["panel_pos"]
        if not (isinstance(pp, (list, tuple)) and len(pp) == 2):
            raise ValueError(f"panel_pos must be [x, y]; got {pp!r}")
        out["panel_pos"] = [int(round(float(c))) for c in pp]
    if out["interval_ms"] not in range(250, 60001):
        raise ValueError("interval_ms must be 250..60000")
    if out["paste_mode"] not in ("paste", "type"):
        raise ValueError("paste_mode must be 'paste' or 'type'")
    if out.get("reader_backend") not in ("gemini", "local"):
        raise ValueError("reader_backend must be 'gemini' or 'local'")
    if out.get("gemini_models") is None:
        out["gemini_models"] = []
    if not isinstance(out["gemini_models"], (list, tuple)):
        raise ValueError("gemini_models must be a list of model names")
    out["gemini_models"] = [str(m).strip() for m in out["gemini_models"] if str(m).strip()]
    try:
        out["gemini_timeout_s"] = float(out.get("gemini_timeout_s", 45.0))
    except (TypeError, ValueError):
        raise ValueError("gemini_timeout_s must be a number") from None
    if not (5.0 <= out["gemini_timeout_s"] <= 300.0):
        raise ValueError("gemini_timeout_s must be 5..300")
    return out


def load(path: Path | None = None) -> dict:
    """Load config; self-healing.

    A config written by an older version may contain a corrupt region (e.g.
    produced when the calibration overlay was not yet mapped — the v1.0.0 bug
    that caused 'Image size … exceeds' capture errors). Such fields are
    DROPPED (set to None) instead of bricking startup: the app opens and asks
    for a fresh calibration; the rest of the settings survive.
    """
    path = Path(path) if path else default_config_path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        raw = json.loads(path.read_text())
    except Exception as e:  # corrupt config must not brick the app
        raise ValueError(f"config file {path} is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError(f"config file {path} must contain a JSON object")

    def probe_key(k, v) -> bool:
        """True if this single key/value pair passes validation on its own."""
        try:
            validate({k: v})
            return True
        except ValueError:
            return False

    clean_raw = dict(raw)
    for k in ("captcha_region", "target_region", "panel_pos"):
        v = clean_raw.get(k)
        if v is not None and not probe_key(k, v):
            clean_raw[k] = None              # drop the corrupt field, keep the rest
    for k in list(clean_raw):
        if k in ("captcha_region", "target_region", "panel_pos", "version"):
            continue
        if not probe_key(k, clean_raw[k]):
            clean_raw.pop(k)                 # unknown-bad scalar -> default
    return validate(clean_raw)


def save(cfg: dict, path: Path | None = None) -> Path:
    path = Path(path) if path else default_config_path()
    payload = json.dumps(validate(cfg), indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".qcaptcha.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload)
        os.replace(tmp, path)  # atomic
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path
