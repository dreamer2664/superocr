#!/usr/bin/env python3
"""qcaptcha screen capture — one small job: screen pixels for a region.

Backends, in order of preference:
  1. Pillow's ImageGrab (Pillow >= 9.2: Windows GDI, macOS screencapture,
     Linux X11 via XCB when Pillow is built with it)
  2. mss (pip install mss) — cross-platform fallback

macOS note: screencapture needs the "Screen Recording" permission granted to
the Python/terminal process (System Settings > Privacy & Security).
"""
from __future__ import annotations

import platform

from PIL import Image

BACKENDS_AVAILABLE: list[str] = []


class CaptureError(RuntimeError):
    pass


def _region_bbox(region) -> tuple[int, int, int, int]:
    x, y, w, h = (int(round(v)) for v in region)
    if w < 8 or h < 8:
        raise CaptureError(f"region too small: {region!r}")
    return (x, y, x + w, y + h)


def _grab_pillow(bbox: tuple[int, int, int, int]) -> Image.Image:
    from PIL import ImageGrab  # local import: keeps module import cheap

    try:
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
    except TypeError:  # older Pillow has no all_screens
        img = ImageGrab.grab(bbox=bbox)
    if img is None or img.width < 2 or img.height < 2:
        raise CaptureError("ImageGrab returned an unusable frame")
    return img.convert("RGB")


def _grab_mss(bbox: tuple[int, int, int, int]) -> Image.Image:
    import mss  # type: ignore

    left, top, right, bottom = bbox
    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _backend_order() -> list[str]:
    order = []
    try:
        from PIL import ImageGrab  # noqa: F401

        order.append("pillow")
    except Exception:
        pass
    try:
        import mss  # noqa: F401

        order.append("mss")
    except Exception:
        pass
    return order


def available_backends() -> list[str]:
    return _backend_order()


def platform_hint() -> str:
    sysname = platform.system()
    if sysname == "Darwin":
        return ("macOS: grant Screen Recording permission to your terminal/Python "
                "(System Settings > Privacy & Security > Screen Recording), then restart.")
    if sysname == "Linux":
        return ("Linux: capture needs an X11 session (XWayland ok for capture; xdotool "
                "injection does NOT work on native Wayland). If ImageGrab fails, "
                "pip install mss.")
    return "Windows: no extra permissions needed for capture."


def grab(region) -> Image.Image:
    """Capture `region` ([x, y, w, h]) from the live screen. RGB Image."""
    bbox = _region_bbox(region)
    errors = []
    for name in _backend_order():
        try:
            return _grab_pillow(bbox) if name == "pillow" else _grab_mss(bbox)
        except Exception as e:  # try the next backend
            errors.append(f"{name}: {e}")
    raise CaptureError(
        "no usable screen-capture backend (" + ("; ".join(errors) or "none installed") + "). "
        + platform_hint()
    )


def screen_size() -> tuple[int, int]:
    """Full virtual screen size for calibration. Raises CaptureError if unknown."""
    try:
        from PIL import ImageGrab

        try:
            img = ImageGrab.grab(all_screens=True)
        except TypeError:
            img = ImageGrab.grab()
        return img.size
    except Exception as e:
        raise CaptureError(f"cannot determine screen size: {e}. {platform_hint()}") from e


def grab_full() -> Image.Image:
    """Full virtual screen (multi-monitor bounding box), RGB Image."""
    try:
        from PIL import ImageGrab

        try:
            return ImageGrab.grab(all_screens=True).convert("RGB")
        except TypeError:
            return ImageGrab.grab().convert("RGB")
    except Exception:
        pass
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception as e:
        raise CaptureError(f"cannot grab the full screen: {e}. {platform_hint()}") from e
