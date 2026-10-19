#!/usr/bin/env python3
"""qcaptcha phone pipeline — reach the device over ADB (USB debugging).

Why this exists: when the captcha lives on a phone, a desktop app cannot see
the right screen and cannot type into the phone's field — no amount of
calibration fixes that. This module talks to the phone itself:

    screenshot (screencap)  ->  what is ON the phone now
    UI hierarchy (uiautomator dump) -> exact widgets, their bounds and text
    input (input tap / input text)  -> type the answer INTO the app

Three uses:
  * `check()`  — is ADB + device + screencap + dump all working? (one JSON)
  * `study()`  — dump the current screen into a folder (screenshot, ui.xml,
                 study.json, REPORT.md) so the UI can be studied properly
                 before anything is automated. Nothing is typed.
  * `PhoneSolver` — solve one captcha on the device, or watch for new ones
                 and solve them as they appear (type + verify).

Design rules:
  * read-only unless asked: `solve_once(type_it=False)` never touches input
  * vision (Gemini) is used when the widget tree cannot describe the captcha
    (WebViews, canvases) — same keys as the desktop app
  * every action is verifiable: after typing we re-dump the UI and look at
    what the field actually contains
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from . import gemini as gemini_mod

# --------------------------------------------------------------------------- adb


class AdbError(RuntimeError):
    pass


def _engine_root() -> Path:
    """Where baseline.py/reader.py live (the bundle root, or the repo root in a
    source checkout). QCAPTCHA_ENGINE wins."""
    env = os.environ.get("QCAPTCHA_ENGINE")
    if env and Path(env).is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    for up in list(here.parents)[:4]:
        if (up / "baseline.py").is_file() or (up / "reader.py").is_file():
            return up
    return here.parents[1]


def find_adb() -> str | None:
    """adb from PATH, or the usual SDK locations (Windows/macOS/Linux)."""
    p = shutil.which("adb")
    if p:
        return p
    for base in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                 str(Path.home() / "Android" / "Sdk"),
                 str(Path.home() / "Library" / "Android" / "sdk")):
        if base:
            exe = Path(base) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
            if exe.is_file():
                return str(exe)
    return None


def mask_serial(serial: str) -> str:
    """Serials are semi-identifying — show only enough to tell devices apart."""
    s = str(serial)
    return (s[:4] + "…") if len(s) > 5 else s + "…"


def esc_input_text(text: str) -> str:
    """`adb shell input text` argument quoting.

    adb re-joins the args into a device-side shell command, so the string needs
    device-shell quoting; `input text` itself uses %s for a space.
    """
    body = str(text).replace(" ", "%s")
    return "'" + body.replace("'", "'\\''") + "'"


class Adb:
    """A very small, defensive ADB client. One device, no side effects."""

    def __init__(self, adb: str | None = None, serial: str | None = None,
                 timeout: float = 30.0):
        self.adb = adb or os.environ.get("QCAPTCHA_ADB") or find_adb() or "adb"
        self.serial = serial or os.environ.get("QCAPTCHA_ADB_SERIAL") or None
        self.timeout = float(timeout)

    # -- plumbing ---------------------------------------------------------
    def _base(self) -> list[str]:
        b = [self.adb]
        if self.serial:
            b += ["-s", self.serial]
        return b

    def run(self, args: list[str], *, binary: bool = False,
            timeout: float | None = None) -> bytes | str:
        cmd = self._base() + list(args)
        try:
            p = subprocess.run(cmd, capture_output=True,
                               timeout=timeout or self.timeout)
        except FileNotFoundError as e:
            raise AdbError(
                f"adb not found at {self.adb!r}. Install Android platform-tools "
                f"(Linux: sudo apt install adb · macOS: brew install --cask "
                f"android-platform-tools · Windows: developer.android.com "
                f"platform-tools), then re-run.") from e
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"adb timed out after {timeout or self.timeout:.0f}s "
                           f"({' '.join(args[:2])}…)") from e
        if p.returncode != 0:
            err = (p.stderr or b"").decode("utf-8", "replace").strip()
            raise AdbError(f"adb {' '.join(args[:2])} failed ({p.returncode}): "
                           f"{err[:300]}")
        return p.stdout if binary else p.stdout.decode("utf-8", "replace")

    def shell(self, *args: str, binary: bool = False,
              timeout: float | None = None) -> bytes | str:
        return self.run(["shell", *args], binary=binary, timeout=timeout)

    def shell_pipe(self, command: str, timeout: float | None = None) -> str:
        """Run a device-side shell pipeline (pipes need sh -c on the device)."""
        return str(self.run(["shell", "sh", "-c", command], timeout=timeout))

    # -- discovery --------------------------------------------------------
    def version(self) -> str:
        return str(self.run(["version"])).splitlines()[0].strip()

    def devices(self) -> list[dict]:
        out = str(self.run(["devices"]))
        devs = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                devs.append({"serial": parts[0], "state": parts[1],
                             "masked": mask_serial(parts[0])})
        return devs

    def pick(self) -> dict:
        """Choose the device to use, with actionable errors."""
        devs = self.devices()
        if self.serial:
            for d in devs:
                if d["serial"] == self.serial:
                    if d["state"] != "device":
                        raise AdbError(f"device {mask_serial(self.serial)} is "
                                       f"'{d['state']}' — accept the USB-debugging "
                                       f"prompt on the phone, then re-run")
                    return d
            raise AdbError(f"device {mask_serial(self.serial)} is not connected "
                           f"(adb devices shows: "
                           f"{[d['masked'] + ':' + d['state'] for d in devs]})")
        ok = [d for d in devs if d["state"] == "device"]
        if not ok:
            if devs:
                raise AdbError("no authorised device: " + ", ".join(
                    f"{d['masked']} is '{d['state']}'" for d in devs)
                    + " — unlock the phone and accept the USB-debugging prompt")
            raise AdbError("no device connected. Plug the phone in with a DATA "
                           "cable, enable Settings → Developer options → USB "
                           "debugging, then accept the prompt on the phone "
                           "(adb devices should list it as 'device')")
        if len(ok) > 1:
            raise AdbError("several devices connected (" +
                           ", ".join(d["masked"] for d in ok) +
                           ") — choose one with --serial <SERIAL>")
        self.serial = ok[0]["serial"]
        return ok[0]

    # -- capture ----------------------------------------------------------
    def screencap(self):
        """PNG screenshot as a PIL image (exec-out, with a two-step fallback)."""
        from PIL import Image
        try:
            data = self.run(["exec-out", "screencap", "-p"], binary=True)
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                return Image.open(io.BytesIO(data)).convert("RGB")
        except AdbError:
            pass
        remote = "/sdcard/qcaptcha_shot.png"
        self.shell("screencap", "-p", remote, timeout=max(self.timeout, 60))
        data = self.run(["exec-out", "cat", remote], binary=True)
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise AdbError("screencap produced no PNG (is the screen locked? "
                           "some devices block capture while locked)")
        return Image.open(io.BytesIO(data)).convert("RGB")

    # -- UI hierarchy -----------------------------------------------------
    def dump_ui(self) -> str:
        """uiautomator dump -> XML text (file first, /dev/tty fallback)."""
        remote = "/sdcard/qcaptcha_ui.xml"
        try:
            self.shell("uiautomator", "dump", remote, timeout=max(self.timeout, 60))
            xml = str(self.run(["exec-out", "cat", remote], timeout=max(self.timeout, 60)))
        except AdbError:
            xml = str(self.run(["exec-out", "uiautomator", "dump", "/dev/tty"],
                               timeout=max(self.timeout, 60)))
        if "<hierarchy" not in xml:
            raise AdbError("uiautomator dump returned no hierarchy XML "
                           f"(got {xml[:80]!r}…)")
        start, end = xml.find("<hierarchy"), xml.rfind("</hierarchy>")
        return xml[start:end + len("</hierarchy>")]

    # -- input ------------------------------------------------------------
    def tap(self, x: int, y: int) -> None:
        self.shell("input", "tap", str(int(x)), str(int(y)))

    def input_text(self, text: str) -> None:
        self.shell("input", "text", esc_input_text(text))

    def adbkeyboard(self, text: str) -> bool:
        """Type via the optional ADBKeyboard IME (unicode-safe). Returns False
        when that IME is not installed."""
        if "adbkeyboard" not in self.ime_list().lower():
            return False
        b64 = __import__("base64").b64encode(text.encode("utf-8")).decode()
        self.shell("am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64)
        return True

    def ime_list(self) -> str:
        try:
            return self.shell_pipe("ime list -s | tr '\\n' ' '")
        except AdbError:
            return ""

    def key(self, code: str) -> None:
        self.shell("input", "keyevent", str(code))

    # -- facts ------------------------------------------------------------
    def prop(self, name: str) -> str:
        try:
            return str(self.shell("getprop", name)).strip()
        except AdbError:
            return ""

    def screen_size(self) -> tuple[int, int]:
        out = str(self.shell("wm", "size"))
        m = re.search(r"(\d+)\s*x\s*(\d+)", out)
        if not m:
            raise AdbError(f"could not read screen size from {out.strip()!r}")
        return int(m.group(1)), int(m.group(2))

    def current_app(self) -> dict:
        """package/activity currently in the foreground (best effort)."""
        out = ""
        for cmd in ("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -4",
                    "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity' | head -4",
                    "dumpsys activity top | grep ACTIVITY | head -2"):
            try:
                got = self.shell_pipe(cmd)
            except AdbError:
                continue
            if got.strip():
                out = got
                break
        pkg = act = ""
        m = re.search(r"([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)", out)
        if m:
            pkg, act = m.group(1), m.group(2)
        return {"package": pkg, "activity": act, "raw": out.strip()[:200]}


# --------------------------------------------------------------------------- UI


def parse_bounds(s: str) -> list[int] | None:
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", s or "")
    if not m:
        return None
    x0, y0, x1, y1 = (int(v) for v in m.groups())
    return [x0, y0, max(0, x1 - x0), max(0, y1 - y0)]


_ATTRS = ("index", "text", "resource-id", "class", "package", "content-desc",
          "clickable", "enabled", "focusable", "focused", "scrollable",
          "long-clickable", "password", "selected", "bounds")


def parse_ui_dump(xml: str) -> list[dict]:
    """XML -> flat node list (dicts) with parsed pixel bounds."""
    root = ET.fromstring(xml)
    out: list[dict] = []

    def walk(node, depth: int):
        for child in node:
            a = child.attrib
            n = {k: a.get(k, "") for k in _ATTRS}
            n["depth"] = depth
            n["bounds"] = parse_bounds(n.get("bounds", ""))
            out.append(n)
            walk(child, depth + 1)

    walk(root, 0)
    return [n for n in out if n.get("bounds")]


def _matches(node: dict, pattern: str) -> bool:
    return bool(re.search(pattern, (node.get("resource-id", "") or "") + " " +
                          (node.get("content-desc", "") or ""), re.I))


def analyze_ui(nodes: list[dict], size: tuple[int, int]) -> dict:
    """Rank the screen's widgets into a captcha box and a text-box.

    Widget-tree first (exact bounds, no guessing). Handles the WebView case by
    saying so — there the solver falls back to vision.
    """
    W, H = size
    screen_area = float(W * H)
    notes: list[str] = []

    def area(n): return float(n["bounds"][2] * n["bounds"][3])

    edits = [n for n in nodes if "edittext" in n.get("class", "").lower()]
    if not edits:
        # some apps use a plain focusable/clickable view for the field
        edits = [n for n in nodes if n.get("focusable") == "true"
                 and n.get("clickable") == "true"
                 and n.get("text") != "" and area(n) < 0.2 * screen_area]
    inputs = sorted(edits, key=lambda n: (
        0 if n.get("focused") == "true" else 1,
        0 if _matches(n, r"input|captcha|code|answer|otp|verify|回复|验证") else 1,
        n["bounds"][1],                       # then top-to-bottom
    ))
    input_node = inputs[0] if inputs else None

    images = []
    for n in nodes:
        cls = n.get("class", "").lower()
        if not any(k in cls for k in ("imageview", "imagebutton", "canvas",
                                      "video", "surface", "textureview")):
            continue
        if n.get("text"):
            continue
        a = area(n)
        if n["bounds"][2] < 48 or n["bounds"][3] < 24 or a > 0.5 * screen_area:
            continue
        images.append(n)
    # also: views that carry an id hint even without an image-ish class
    for n in nodes:
        if n not in images and _matches(n, r"captcha|verify_code|verifycode|challenge|vcode|img_code"):
            if area(n) < 0.5 * screen_area and n["bounds"][2] >= 48:
                images.append(n)

    def cap_score(n):
        b = n["bounds"]
        a = area(n)
        s = 0.0
        if _matches(n, r"captcha|verify|challenge|vcode|img|pic|code"):
            s += 3.0
        if input_node:                                  # captchas sit ABOVE fields
            iy = input_node["bounds"][1]
            if b[1] < iy:
                s += 2.0 - min(1.5, (iy - (b[1] + b[3])) / max(1.0, H * 0.35))
            else:
                s -= 1.0
            ix = input_node["bounds"][0]
            if abs(b[0] - ix) < W * 0.15:
                s += 0.5
        if 0.005 * screen_area <= a <= 0.25 * screen_area:
            s += 1.5
        ar = b[2] / max(1.0, b[3])
        if 1.2 <= ar <= 6.5:
            s += 1.0
        if n.get("clickable") == "true" and "imageview" not in n.get("class", "").lower():
            s -= 0.5
        return -s

    best = sorted(images, key=cap_score)[0] if images else None

    webviews = [n for n in nodes if "webview" in n.get("class", "").lower()]
    if webviews and not best:
        notes.append("a WebView is on screen and no captcha-like widget was "
                     "found outside it — the captcha is probably INSIDE the "
                     "WebView; use the vision fallback (keys required)")
    if not input_node:
        notes.append("no EditText found — the field may be inside a WebView; "
                     "tap-to-focus will be skipped unless vision finds a box")
    if not best:
        notes.append("no captcha widget found in the widget tree")
    return {
        "input": list(input_node["bounds"]) if input_node else None,
        "captcha": list(best["bounds"]) if best else None,
        "input_node": input_node,
        "captcha_node": best,
        "notes": notes,
    }


# --------------------------------------------------------------------------- check


def check(adb: Adb | None = None) -> dict:
    adb = adb or Adb()
    rep: dict = {"adb": adb.adb, "serial": mask_serial(adb.serial) if adb.serial else None}
    try:
        rep["version"] = adb.version()
    except AdbError as e:
        rep.update(ok=False, error=str(e))
        return rep
    try:
        rep["devices"] = [f"{d['masked']}:{d['state']}" for d in adb.devices()]
        dev = adb.pick()
        rep["serial"] = dev["masked"]
        rep["android"] = adb.prop("ro.build.version.release")
        rep["model"] = adb.prop("ro.product.model")
        w, h = adb.screen_size()
        rep["screen"] = f"{w}x{h}"
        shot = adb.screencap()
        rep["screencap"] = f"ok {shot.width}x{shot.height}"
        xml = adb.dump_ui()
        rep["ui_dump"] = f"ok {len(xml)} bytes"
        rep["ime"] = adb.ime_list().strip() or "(default)"
        app = adb.current_app()
        rep["foreground"] = f"{app['package']}/{app['activity']}" if app["package"] else "(unknown)"
        rep["ok"] = True
    except AdbError as e:
        rep.update(ok=False, error=str(e))
    return rep


# --------------------------------------------------------------------------- study


def study(adb: Adb | None = None, outdir: str | Path = "qcaptcha-phone-study",
          *, shot: bool = True) -> dict:
    """Collect everything about the current screen for UI study. Types nothing."""
    adb = adb or Adb()
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    dev = adb.pick()
    img = adb.screencap()
    xml = adb.dump_ui()
    nodes = parse_ui_dump(xml)
    an = analyze_ui(nodes, img.size)
    app = adb.current_app()

    (out / "ui.xml").write_text(xml)
    if shot:
        img.save(out / "screenshot.png")
    if an["captcha"]:
        x, y, w, h = an["captcha"]
        img.crop((x, y, x + w, y + h)).save(out / "captcha_crop.png")
    info = {
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": {"serial": dev["masked"], "model": adb.prop("ro.product.model"),
                   "android": adb.prop("ro.build.version.release"),
                   "screen": f"{img.width}x{img.height}"},
        "foreground": app,
        "candidates": {"captcha": an["captcha"], "input": an["input"]},
        "notes": an["notes"],
        "nodes": [{k: n.get(k) for k in ("class", "resource-id", "text",
                                         "content-desc", "bounds", "clickable",
                                         "focusable", "focused", "password")}
                  for n in nodes],
    }
    (out / "study.json").write_text(json.dumps(info, indent=2))

    rows = ["| # | class | id | text/desc | bounds | taps? |",
            "|---|---|---|---|---|---|"]
    for i, n in enumerate(nodes):
        txt = (n.get("text") or n.get("content-desc") or "")[:28]
        rows.append(f"| {i} | {n.get('class','').split('.')[-1][:22]} | "
                    f"{(n.get('resource-id','') or '').split('/')[-1][:24]} | "
                    f"{txt} | {n['bounds']} | "
                    f"{'tap' if n.get('clickable') == 'true' else ''} |")
    report = f"""# qcaptcha phone study — {info['ts_utc']}

**Device:** {info['device']['model']} · Android {info['device']['android']} · \
{info['device']['screen']} · serial {info['device']['serial']}
**Foreground:** `{app['package']}/{app['activity']}`

## What the analyzer thinks
* **captcha box:** `{an['captcha']}`  (x, y, w, h in pixels)
* **text box:** `{an['input']}`
* notes: {'; '.join(an['notes']) if an['notes'] else '—'}

Captcha widget: `{(an['captcha_node'] or {}).get('class','—')}` id \
`{(an['captcha_node'] or {}).get('resource-id','—')}`
Text widget: `{(an['input_node'] or {}).get('class','—')}` id \
`{(an['input_node'] or {}).get('resource-id','—')}`

## Every widget on this screen
{chr(10).join(rows)}

---
Files in this folder: `ui.xml` (raw hierarchy) · `study.json` (parsed) · \
`screenshot.png`{' (omit with --no-shot)' if shot else ' (not saved)'} · \
`captcha_crop.png` (the crop the reader would see, when a box was found).

**Safe to share:** REPORT.md + study.json + captcha_crop.png.
`screenshot.png` may contain personal data — your call.
"""
    (out / "REPORT.md").write_text(report)
    return {"dir": str(out), "device": info["device"], "foreground": app,
            "candidates": info["candidates"], "notes": info["notes"],
            "files": sorted(p.name for p in out.iterdir())}


# --------------------------------------------------------------------------- solve


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PhoneSolver:
    """Solve captchas on the phone: dump+vision to locate, reader to read,
    ADB to type, then RE-DUMP to verify what the field actually contains."""

    def __init__(self, cfg: dict, adb: Adb | None = None, reader=None, *,
                 client: gemini_mod.GeminiClient | None = None,
                 history: Path | None = None, log_fn=None):
        self.cfg = cfg
        self.adb = adb or Adb(adb=cfg.get("phone_adb") or None,
                              serial=cfg.get("phone_serial") or None,
                              timeout=float(cfg.get("phone_timeout_s", 30.0)))
        self.reader = reader
        self.client = client
        self.history = history
        self.log = log_fn or (lambda *a, **k: None)
        self._delivered_hash: str | None = None
        self._delivered_text: str | None = None
        self._consecutive_errors = 0

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _crop_hash(img) -> str:
        return hashlib.sha1(img.tobytes()).hexdigest()

    def _write_row(self, row: dict) -> None:
        if not self.history:
            return
        try:
            import csv
            from .solver import HISTORY_COLUMNS
            self.history.parent.mkdir(parents=True, exist_ok=True)
            new = not self.history.exists()
            with self.history.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, extrasaction="ignore")
                if new:
                    w.writeheader()
                w.writerow(row)
        except Exception as e:
            self.log(f"history log failed: {e}")

    def _verify(self, expected: str, input_box) -> dict:
        """Re-dump and look at what the field really contains."""
        try:
            nodes = parse_ui_dump(self.adb.dump_ui())
        except AdbError as e:
            return {"verified": None, "note": f"verify skipped: {e}"}
        x, y, w, h = input_box
        cands = []
        for n in nodes:
            b = n["bounds"]
            if not b:
                continue
            overlap = (min(b[0] + b[2], x + w) - max(b[0], x)) * \
                      (min(b[1] + b[3], y + h) - max(b[1], y))
            if overlap > 0.3 * (w * h):
                cands.append((n, overlap))
        if not cands:
            return {"verified": None, "note": "field not found in the re-dump"}
        # the field itself, not the container around it: a node WITH text wins;
        # otherwise the smallest overlap (the innermost widget)
        with_text = [c for c in cands if (c[0].get("text") or "").strip()]
        node = (min(with_text, key=lambda c: c[1])[0] if with_text
                else min(cands, key=lambda c: c[1])[0])
        got = (node.get("text") or "").strip()
        ok = got == expected.strip()
        return {"verified": ok, "field_text": got,
                "note": "" if ok else "field does not match the read"}

    # -- the one solve ----------------------------------------------------
    def solve_once(self, *, type_it: bool = False, verify: bool | None = None,
                   force: bool = False) -> dict:
        t0 = time.perf_counter()
        row = {"ts_utc": _now(), "text": "", "raw_conf": None, "ms": 0,
               "delivered": False, "mode": "", "backend": "", "detect": "",
               "seconds": None, "error": None, "target": "phone",
               "verified": None, "captcha_region": None, "target_region": None}
        try:
            shot = self.adb.screencap()
            nodes = parse_ui_dump(self.adb.dump_ui())
            an = analyze_ui(nodes, shot.size)
            cap, inp = an["captcha"], an["input"]
            row.update(detect="ui-dump", captcha_region=cap, target_region=inp)
            text = ""
            if cap is None and self.client is not None:
                res = gemini_mod.solve_page(self.client, shot)
                cap, inp = res.get("captcha") or inp, res.get("input") or inp
                text = (res.get("text") or "").strip()
                row.update(detect="vision", captcha_region=cap, target_region=inp,
                           seconds=res.get("seconds"))
                self.log("captcha not in the widget tree — vision locate used")
            if cap is None:
                row["error"] = ("no captcha found (widget tree had none and "
                                "vision is " + ("unavailable: no keys"
                                                if self.client is None else "empty") + ")")
                return row
            x, y, w, h = [int(v) for v in cap]
            crop = shot.crop((x, y, x + w, y + h))
            if (not force and self._delivered_hash is not None
                    and self._crop_hash(crop) == self._delivered_hash):
                row["error"] = "duplicate (same captcha already answered)"
                row["detect"] += "+dup"
                return row
            if not text:
                if self.reader is None:
                    row["error"] = "no reader configured"
                    return row
                res = self.reader.read_with_retry(
                    crop, retry_upscale=self.cfg.get("retry_upscale", True))
                text = (res.get("text") or "").strip()
                row.update(raw_conf=res.get("conf"), backend=res.get("backend", ""),
                           seconds=res.get("seconds"))
            if not text:
                row["error"] = "empty read"
                return row
            row["text"] = text
            if not type_it:
                row["mode"] = "read-only"
                return row
            if not inp:
                row["error"] = "no text box located — cannot type"
                return row
            ix, iy, iw, ih = [int(v) for v in inp]
            self.adb.tap(ix + iw // 2, iy + ih // 2)
            time.sleep(max(0, int(self.cfg.get("phone_pause_after_tap_ms", 250))) / 1000.0)
            used = "input"
            if any(ord(c) > 127 for c in text) and self.adb.adbkeyboard(text):
                used = "adbkeyboard"
            else:
                self.adb.input_text(text)
            row.update(delivered=True, mode=used)
            if verify is None:
                verify = bool(self.cfg.get("phone_verify", True))
            if verify:
                v = self._verify(text, inp)
                row.update(verified=v.get("verified"), mode=used if v.get("verified")
                           else used + "!")
                if v.get("verified") is False:
                    row["error"] = f"typed but not verified: {v.get('note')}"
                elif v.get("verified") is None:
                    row["error"] = f"typed, could not verify ({v.get('note')})"
            if row.get("error") is None:
                self._delivered_hash = self._crop_hash(crop)
                self._delivered_text = text
                self._consecutive_errors = 0
            else:
                self._consecutive_errors += 1
        except AdbError as e:
            row["error"] = f"adb: {e}"
            self._consecutive_errors += 1
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
            self._consecutive_errors += 1
        finally:
            row["ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            self._write_row(row)
        return row

    # -- the watch loop (the 15-second-timer answer) -----------------------
    def run_loop(self, on_event, interval_ms: int | None = None,
                 stop_after_errors: int = 5, max_cycles: int | None = None) -> None:
        interval = float(interval_ms if interval_ms is not None
                         else self.cfg.get("interval_ms", 1500)) / 1000.0
        cycles = 0
        while True:
            cycles += 1
            row = self.solve_once(type_it=True)
            on_event(row)
            if (row.get("error") or "").startswith("duplicate"):
                self._consecutive_errors = 0      # normal: the page has not changed
            if self._consecutive_errors >= stop_after_errors:
                on_event({"_stopped": True,
                          "error": f"stopped after {self._consecutive_errors} "
                                   f"consecutive errors — last: {row.get('error')}"})
                return
            if max_cycles is not None and cycles >= max_cycles:
                return
            time.sleep(max(0.2, interval))


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    """Small standalone entry: python3 -m qcaptcha.phone {check,study,once,arm}"""
    import argparse
    ap = argparse.ArgumentParser(prog="qcaptcha.phone",
                                 description="qcaptcha phone pipeline (ADB)")
    ap.add_argument("cmd", choices=["check", "study", "once", "arm"])
    ap.add_argument("--adb", default=None)
    ap.add_argument("--serial", default=None)
    ap.add_argument("--out", default="qcaptcha-phone-study")
    ap.add_argument("--no-shot", action="store_true")
    ap.add_argument("--type", dest="type_it", action="store_true")
    a = ap.parse_args(argv)
    adb = Adb(adb=a.adb, serial=a.serial)
    if a.cmd == "check":
        print(json.dumps(check(adb), indent=2))
        return 0
    if a.cmd == "study":
        print(json.dumps(study(adb, a.out, shot=not a.no_shot), indent=2))
        return 0
    # once / arm need the app's config + readers
    from . import config as config_mod
    from .readers import make_reader
    from .engine import ReaderEngine
    cfg = config_mod.load()
    eng = ReaderEngine(_engine_root())
    reader, note = make_reader(cfg, eng)
    client = getattr(reader, "client", None)
    solver = PhoneSolver(cfg, adb, reader, client=client)
    if a.cmd == "once":
        print(json.dumps(solver.solve_once(type_it=a.type_it), indent=2))
        return 0
    solver.run_loop(lambda row: print(json.dumps(row, default=str), flush=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
