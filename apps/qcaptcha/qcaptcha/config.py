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
}


def default_config_path() -> Path:
    env = os.environ.get("QCAPTCHA_CONFIG")
    if env:
        return Path(env)
    return Path.home() / ".qcaptcha.json"


def _valid_region(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(v, (int, float)) for v in value)
        and value[2] >= 8
        and value[3] >= 8
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
    return out


def load(path: Path | None = None) -> dict:
    path = Path(path) if path else default_config_path()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        raw = json.loads(path.read_text())
    except Exception as e:  # corrupt config must not brick the app
        raise ValueError(f"config file {path} is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError(f"config file {path} must contain a JSON object")
    return validate(raw)


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
