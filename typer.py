#!/usr/bin/env python3
"""superocr typer — S4: image -> recognised text -> a target field (t-20261011-7b9f).

The product shape from JOBS.md: a file (or a captured screen region) in,
the text typed into a target. Targets are OPT-IN and explicit:

    --target stdout            print only (default; safe everywhere)
    --target file:PATH         append the text + newline to PATH
    --target xdo               xdotool types into whatever field has focus
    --target clipboard         xclip/pbcopy puts it on the clipboard

xdo/clipboard require the tool to exist; where it does not, the typer says
so plainly and offers stdout instead - no silent failure, no half-typing.

Where this may and may not be used (README, repeated here): the typer types
into a field THE USER aimed it at. Never wire it into password prompts,
payment confirmations, or anything that acts on what it types; it is a
transcription convenience, not an automation authority.

Screen regions: headless-friendly contract - capture with any external tool
(grim, import, gnome-screenshot) and pipe the file; --crop WxH+X+Y slices a
region out of the given image. No hidden screen grabbing.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

import generator as G
import reader as R
import preclassify as P

ALL_FAMILIES = ["easy"] + [f for f in G.FAMILIES if f != "easy"]


def crop(img: Image.Image, spec: str) -> Image.Image:
    """WxH+X+Y, x11 geometry style."""
    parts = spec.replace("x", "+").split("+")
    W, H, X, Y = (int(p) for p in parts)
    return img.crop((X, Y, min(img.width, X + W), min(img.height, Y + H)))


def recognise(img: Image.Image, family: str) -> tuple[str, list[float], str]:
    """Read one image. A pinned family runs exactly that chain. 'auto' asks
    preclassify which family the image looks like and runs that ONE chain
    (t-20261012-5c63). The old auto ran all 13 chains and picked by average
    glyph confidence: 8-21 s per image, and the arbitration was gameable —
    a family that decoded garbage glyphs confidently beat the right one
    (an easy image was regularly read as 'cut': 32/104 correct family vs
    84/104 for trusting the pre-classifier). Fallback stays bounded: only
    if a chain fails to produce a usable read does the next candidate run.
    """
    if family != "auto":
        text, conf, _ = R.read_chain(img, family)
        return text, conf, family
    text, conf, fam = "", [], P.rank(img)[0]
    for fam in P.rank(img):
        try:
            text, conf, _ = R.read_chain(img, fam)
        except SystemExit:
            continue
        if len(conf) >= 3:
            break
    return text, conf, fam



def deliver(text: str, target: str) -> str:
    """Returns the method actually used; raises SystemExit with guidance."""
    if target == "stdout":
        print(text)
        return "stdout"
    if target == "file" or target.startswith("file:"):
        path = Path(target.split(":", 1)[1])
        with open(path, "a") as f:
            f.write(text + "\n")
        return f"file:{path}"
    if target == "xdo":
        if not shutil.which("xdotool"):
            sys.exit("error: xdotool not installed - use --target stdout or "
                     "file:PATH, or install xdotool on a real desktop")
        subprocess.run(["xdotool", "type", "--clear-modifiers", "--delay", "20",
                        "--", text], check=True)
        return "xdo"
    if target == "clipboard":
        tool = shutil.which("xclip") or shutil.which("pbcopy")
        if not tool:
            sys.exit("error: no clipboard tool (xclip/pbcopy) - use "
                     "--target stdout or file:PATH")
        with subprocess.Popen([tool] + (["-selection", "clipboard"] if "xclip" in tool else []),
                              stdin=subprocess.PIPE) as p:
            p.communicate(text.encode())
        return "clipboard"
    sys.exit(f"error: unknown target {target!r} (stdout | file:PATH | xdo | clipboard)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="superocr typer (opt-in targets)")
    ap.add_argument("image", help="PNG/JPG file (pipe a screen capture in)")
    ap.add_argument("--family", default="auto")
    ap.add_argument("--crop", help="region WxH+X+Y sliced from the image")
    ap.add_argument("--target", default="stdout")
    args = ap.parse_args(argv)
    img = Image.open(args.image)
    if args.crop:
        img = crop(img, args.crop)
    text, conf, fam = recognise(img, args.family)
    method = deliver(text, args.target)
    print(f"[typer] family={fam} glyphs={len(conf)} target={method}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
