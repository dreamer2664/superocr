#!/usr/bin/env python3
"""qcaptcha input injection — put the read text into somebody else's text box.

Two delivery modes:
  paste  (default) — clipboard + Ctrl+V (Cmd+V on macOS). Fast, no character
                     drops. The clipboard is restored to its previous contents
                     afterwards unless disabled.
  type             — send the characters one by one (Unicode-capable on
                     Windows via SendInput; xdotool type on Linux; System
                     Events keystroke on macOS).

Backends per OS (first available wins, all injectable for tests via `BACKENDS`):
  Linux   : pynput (if installed) -> xdotool -> error with an install hint
  macOS   : osascript (System Events — needs Accessibility permission)
  Windows : native ctypes SendInput (no dependency)

The module is deliberately small and dependency-optional: the app must run on
a bare python + Pillow + numpy install, and grow capabilities if the user has
pynput or xdotool.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import threading
import time

SYSTEM = platform.system()


class InjectError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: float = 15.0) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise InjectError(f"{cmd[0]} failed ({p.returncode}): {p.stderr.strip()[:200]}")


# --------------------------------------------------------------------------
# clipboard
# --------------------------------------------------------------------------

class Clipboard:
    """Best-effort clipboard get/set per OS. get() may return None (unknown)."""

    def __init__(self) -> None:
        self.kind = self._probe()

    def _probe(self) -> str:
        if SYSTEM == "Darwin":
            return "pbcopy" if shutil.which("pbcopy") else "none"
        if SYSTEM == "Windows":
            return "win32"
        for tool in ("wl-copy", "xclip", "xsel"):
            if shutil.which(tool):
                return tool
        return "none"

    def _xclip_style(self) -> list[str]:
        if self.kind == "xclip":
            return ["xclip", "-selection", "clipboard"]
        if self.kind == "xsel":
            return ["xsel", "--clipboard"]
        return []

    def get(self) -> str | None:
        try:
            if self.kind == "pbcopy":
                return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout
            if self.kind == "win32":
                return _win_get_clipboard()
            if self.kind in ("xclip", "xsel"):
                return subprocess.run(self._xclip_style() + ["-o"], capture_output=True,
                                      text=True, timeout=5).stdout
            if self.kind == "wl-copy" and shutil.which("wl-paste"):
                return subprocess.run(["wl-paste", "--no-newline"], capture_output=True,
                                      text=True, timeout=5).stdout
        except Exception:
            return None
        return None

    def set(self, text: str) -> bool:
        """Returns True if the clipboard was set by us."""
        try:
            if self.kind == "pbcopy":
                subprocess.run(["pbcopy"], input=text, text=True, timeout=5, check=True)
                return True
            if self.kind == "win32":
                _win_set_clipboard(text)
                return True
            if self.kind in ("xclip", "xsel"):
                subprocess.run(self._xclip_style() + ["-i"], input=text, text=True,
                               timeout=5, check=True)
                return True
            if self.kind == "wl-copy":
                subprocess.run(["wl-copy"], input=text, text=True, timeout=5, check=True)
                return True
        except Exception as e:
            raise InjectError(f"could not set the clipboard ({self.kind}): {e}") from e
        return False  # "none": caller falls back to typing


def _win_set_clipboard(text: str) -> None:
    import ctypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 2
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    if not u32.OpenClipboard(None):
        raise InjectError("OpenClipboard failed")
    try:
        u32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        h = k32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h:
            raise InjectError("GlobalAlloc failed")
        ptr = k32.GlobalLock(h)
        ctypes.memmove(ptr, buf, size)
        k32.GlobalUnlock(h)
        if not u32.SetClipboardData(CF_UNICODETEXT, h):
            raise InjectError("SetClipboardData failed")
    finally:
        u32.CloseClipboard()


def _win_get_clipboard() -> str | None:
    import ctypes

    CF_UNICODETEXT = 13
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    if not u32.OpenClipboard(None):
        return None
    try:
        if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = k32.GlobalLock(h)
        if not ptr:
            return None
        try:
            return ctypes.c_wchar_p(ptr).value
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


# --------------------------------------------------------------------------
# mouse click (focus) + key delivery
# --------------------------------------------------------------------------

def _click_linux(x: int, y: int) -> None:
    if shutil.which("xdotool"):
        _run(["xdotool", "mousemove", "--sync", str(x), str(y), "click", "1"])
        return
    try:
        from pynput.mouse import Button, Controller  # type: ignore

        c = Controller()
        c.position = (x, y)
        time.sleep(0.05)
        c.click(Button.left)
        return
    except ImportError:
        pass
    raise InjectError("no click backend on Linux: install xdotool (apt install xdotool) "
                      "or pip install pynput")


def _click_macos(x: int, y: int) -> None:
    # System Events cannot move the pointer reliably; cliclick is the honest
    # second option. osascript "click at" exists on some versions but is flaky.
    if shutil.which("cliclick"):
        _run(["cliclick", f"c:{x},{y}"])
        return
    script = (f'tell application "System Events" to click at {{{x}, {y}}}')
    try:
        _run(["osascript", "-e", script])
    except InjectError as e:
        raise InjectError(
            "macOS click needs Accessibility permission for your terminal (System "
            "Settings > Privacy & Security > Accessibility), or install cliclick "
            "(brew install cliclick)") from e


def _click_windows(x: int, y: int) -> None:
    import ctypes

    u32 = ctypes.windll.user32
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    u32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    u32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP


def click(x: int, y: int) -> None:
    if SYSTEM == "Linux":
        _click_linux(x, y)
    elif SYSTEM == "Darwin":
        _click_macos(x, y)
    elif SYSTEM == "Windows":
        _click_windows(x, y)
    else:
        raise InjectError(f"unsupported OS: {SYSTEM}")


def _chord_linux(ctrl: bool = False, cmd: bool = False) -> None:
    key = "ctrl+v" if ctrl else "cmd+v"
    if shutil.which("xdotool"):
        _run(["xdotool", "key", "--clearmodifiers", key])
        return
    try:
        from pynput.keyboard import Controller, Key  # type: ignore

        c = Controller()
        with c.pressed(Key.ctrl):
            c.press("v")
            c.release("v")
        return
    except ImportError:
        pass
    raise InjectError("no key backend on Linux: install xdotool (apt install xdotool) "
                      "or pip install pynput")


def _chord_macos() -> None:
    script = 'tell application "System Events" to keystroke "v" using command down'
    try:
        _run(["osascript", "-e", script])
    except InjectError as e:
        raise InjectError(
            "macOS paste needs Accessibility permission for your terminal (System "
            "Settings > Privacy & Security > Accessibility)") from e


def _chord_windows() -> None:
    import ctypes

    u32 = ctypes.windll.user32
    VK_CONTROL, VK_V = 0x11, 0x56
    KEYUP = 0x0002
    u32.keybd_event(VK_CONTROL, 0, 0, 0)
    u32.keybd_event(VK_V, 0, 0, 0)
    u32.keybd_event(VK_V, 0, KEYUP, 0)
    u32.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def paste_chord() -> None:
    if SYSTEM == "Linux":
        _chord_linux(ctrl=True)
    elif SYSTEM == "Darwin":
        _chord_macos()
    elif SYSTEM == "Windows":
        _chord_windows()
    else:
        raise InjectError(f"unsupported OS: {SYSTEM}")


def _type_linux(text: str) -> None:
    if shutil.which("xdotool"):
        _run(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text], timeout=60)
        return
    try:
        from pynput.keyboard import Controller  # type: ignore

        Controller().type(text)
        return
    except ImportError:
        pass
    raise InjectError("no typing backend on Linux: install xdotool or pip install pynput")


def _type_macos(text: str) -> None:
    # quote for AppleScript: escape backslashes and double quotes
    q = text.replace("\\", "\\\\").replace('"', '\\"')
    try:
        _run(["osascript", "-e", f'tell application "System Events" to keystroke "{q}"'], timeout=60)
    except InjectError as e:
        raise InjectError("macOS typing needs Accessibility permission for your terminal") from e


def _type_windows(text: str) -> None:
    import ctypes

    u32 = ctypes.windll.user32
    KEYEVENTF_UNICODE, KEYEVENTF_KEYUP = 0x0004, 0x0002
    for ch in text:
        code = ord(ch)
        u32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
        u32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
        time.sleep(0.004)


def type_text(text: str) -> None:
    if SYSTEM == "Linux":
        _type_linux(text)
    elif SYSTEM == "Darwin":
        _type_macos(text)
    elif SYSTEM == "Windows":
        _type_windows(text)
    else:
        raise InjectError(f"unsupported OS: {SYSTEM}")


# --------------------------------------------------------------------------
# the one call the solver makes
# --------------------------------------------------------------------------

# Test hook: a test may replace any of these.
BACKENDS = {
    "click": click,
    "paste_chord": paste_chord,
    "type_text": type_text,
    "clipboard": None,          # lazily created Clipboard()
    "sleep": time.sleep,
}


def _clipboard() -> Clipboard:
    if BACKENDS["clipboard"] is None:
        BACKENDS["clipboard"] = Clipboard()
    return BACKENDS["clipboard"]


def deliver(text: str, target_region, *, mode: str = "paste",
            restore_clipboard: bool = True, pause_before_paste_ms: int = 120,
            focus_first: bool = True) -> dict:
    """Focus the target region's text box and deliver `text`.

    Returns a dict of facts for the log: mode_used, delivered, clipboard_used,
    restored, backend errors (if any).
    """
    from . import config  # noqa: F401  (kept for symmetry; regions validated upstream)

    x, y, w, h = (int(round(v)) for v in target_region)
    info = {"mode_used": None, "delivered": False, "clipboard_used": False,
            "restored": False, "error": None}
    if focus_first:
        try:
            BACKENDS["click"](x + w // 2, y + h // 2)
        except Exception as e:
            info["error"] = f"click: {e}"
            raise InjectError(f"could not focus the text box: {e}") from e
    BACKENDS["sleep"](max(0, int(pause_before_paste_ms)) / 1000.0)

    if mode == "paste":
        cb = _clipboard()
        saved = None
        if restore_clipboard:
            saved = cb.get()
        set_ok = False
        try:
            set_ok = cb.set(text)
        except InjectError:
            set_ok = False
        if set_ok:
            try:
                BACKENDS["paste_chord"]()
                info.update(mode_used="paste", delivered=True, clipboard_used=True)
            except Exception as e:
                info["error"] = f"paste chord: {e}"
                raise InjectError(f"clipboard set but paste failed: {e}") from e
            finally:
                if restore_clipboard and saved is not None:
                    def _restore():
                        BACKENDS["sleep"](0.6)  # give the target app time to read the clipboard
                        try:
                            cb.set(saved)
                            info["restored"] = True
                        except Exception:
                            pass
                    threading.Thread(target=_restore, daemon=True).start()
            return info
        # no clipboard backend: fall through to typing
        mode = "type"

    BACKENDS["type_text"](text)
    info.update(mode_used="type", delivered=True)
    return info


def backend_report() -> dict:
    """What this machine can actually do — surfaced by the launcher preflight."""
    rep = {"os": SYSTEM, "python": sys.version.split()[0], "clipboard": Clipboard().kind,
           "click": None, "keys": None}
    if SYSTEM == "Linux":
        if shutil.which("xdotool"):
            rep.update(click="xdotool", keys="xdotool")
        else:
            try:
                import pynput  # type: ignore  # noqa: F401

                rep.update(click="pynput", keys="pynput")
            except ImportError:
                rep.update(click="MISSING", keys="MISSING")
        if not (sys.platform.startswith("linux") and "WAYLAND_DISPLAY" in __import__("os").environ):
            pass
    elif SYSTEM == "Darwin":
        rep.update(click="osascript" if shutil.which("osascript") else "MISSING",
                   keys="osascript" if shutil.which("osascript") else "MISSING")
    elif SYSTEM == "Windows":
        rep.update(click="SendInput", keys="SendInput")
    return rep
