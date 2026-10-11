#!/usr/bin/env python3
"""Tile Carlo's four reference sheets into single-captcha PNGs (t-20261011-4e49).

Deterministic: same sheets in -> same tiles out (byte-identical PNGs; specs are
hard-coded pixel boxes measured on the committed JPGs). Tiles are NATIVE
RESOLUTION crops, never enhanced — the bench must meet the real pixels.

    python3 tools/tile_reference.py            # regenerate reference/tiles/
    python3 tools/tile_reference.py --check    # verify tiles match the spec (sha256)

Labels live in reference/labels.json and are authored by an agent who read the
tiles with certainty; tests/test_reference_pack.py enforces the pact between
the two.
"""
import argparse
import hashlib
import json
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(ROOT, "reference")
TILES = os.path.join(REF, "tiles")

# captchas1.jpg 411x486: 2 cols x 7 rows of ~205x69.4px cells; each cell has a
# ~16px caption above the captcha strip.
SHEET1 = "captchas1.jpg"
NAMES1 = ["collage", "snow", "corrosion", "spiderweb", "crossshadow", "spiderweb2",
          "crossshadow2", "split", "cut", "split2", "darts", "stitch",
          "distortion", "strippy"]

# captchas2.jpg 609x503: four stacked tutorial panels, x=10..495 (the ✓/✗ grade
# column starts at x≈495). Panel 1 is a composite: a tiny plate photo on the
# left and the solver's printed answer on the right — two tiles.
PANELS2 = [
    ("p1-photo",  (0,   8, 246, 107)),
    ("p1-digits", (250, 8, 492, 107)),
    ("p2-paypal", (0, 110, 492, 264)),
    ("p3-dark",   (0, 266, 492, 396)),
    ("p4-noise",  (0, 398, 495, 502)),
]

# captchas3.jpg 350x329: 2 cols x 6 rows of 175x54.83px cells, no captions.
SHEET3 = "captchas3.jpg"

# Screenshot 2026-10-09 211136.png 1026x425: one live captcha in the solver UI.
SHOT = ("Screenshot 2026-10-09 211136.png", (205, 20, 460, 110))


def _grid(img, nx, ny, names, caption_px, margin, caption_overrides=None):
    W, H = img.size
    cw, ch = W / nx, H / ny
    for r in range(ny):
        cap = (caption_overrides or {}).get(r, caption_px)
        for c in range(nx):
            box = (int(c * cw) + margin,
                   int(r * ch) + cap + margin,
                   int((c + 1) * cw) - margin,
                   int((r + 1) * ch) - margin)
            yield names[r * nx + c], img.crop(box)


def tile_spec():
    """Yields (relpath, Image) for every tile, in stable order."""
    img1 = Image.open(os.path.join(REF, SHEET1)).convert("RGB")
    for name, t in _grid(img1, 2, 7, NAMES1, caption_px=20, margin=2,
                           caption_overrides={6: 22}):
        yield os.path.join("captchas1", f"{name}.png"), t
    img2 = Image.open(os.path.join(REF, "captchas2.jpg")).convert("RGB")
    for name, box in PANELS2:
        yield os.path.join("captchas2", f"{name}.png"), img2.crop(box)
    img3 = Image.open(os.path.join(REF, SHEET3)).convert("RGB")
    names3 = [f"t{i:02d}" for i in range(1, 13)]
    for name, t in _grid(img3, 2, 6, names3, caption_px=0, margin=1):
        yield os.path.join("captchas3", f"{name}.png"), t
    fname, box = SHOT
    img4 = Image.open(os.path.join(REF, fname)).convert("RGB")
    yield os.path.join("screenshot", "live-captcha.png"), img4.crop(box)


def sha256(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify on-disk tiles match what the spec generates")
    args = ap.parse_args()

    if args.check:
        mismatches = []
        for rel, img in tile_spec():
            path = os.path.join(TILES, rel)
            if not os.path.exists(path):
                mismatches.append(f"missing: {rel}")
                continue
            import io
            buf = io.BytesIO()
            img.save(buf, "PNG")
            if hashlib.sha256(buf.getvalue()).hexdigest() != sha256(path):
                mismatches.append(f"different bytes: {rel}")
        if mismatches:
            print("\n".join(mismatches))
            raise SystemExit(1)
        print(f"OK: all {len(list(tile_spec()))} tiles match the spec")
        return

    manifest = {}
    for rel, img in tile_spec():
        path = os.path.join(TILES, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path, "PNG")
        manifest["tiles/" + rel.replace(os.sep, "/")] = sha256(path)
    with open(os.path.join(TILES, "manifest.sha256.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {len(manifest)} tiles + manifest")


if __name__ == "__main__":
    main()
