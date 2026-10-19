#!/usr/bin/env python3
"""S73 — case-twin probe corpus for the S70 case instrument
(t-20261014-1759).

200 items whose letters are recoverable but whose CASE is ambiguous:
every glyph is drawn from the x-height twin set {o,O, c,C, s,S} (same
shape, different height — the template matcher's classic confusion
class). Two variants:

  clean  — plain draw_label render, no degradation: the x-height cue
           is fully available, so an image-side case instrument has
           everything it needs (the honest upper bound for S70).
  strike — same render + one horizontal strikethrough line through the
           text band (stitch-seam style), which interferes with height
           estimation (the hard arm for S70).

Canonical recipes are NOT touched: this composes the generator's
public drawing helpers (paper/draw_label/load_font) with a fresh seed
(default 973; never 1/2/3/4/53). Images are generated, not committed;
the committed identity is manifest.jsonl + its sha256 + this tool.

Usage:
  python3 tools/s73_case_twin_corpus.py [--seed 973] [--out reports/case-corpus/2026-10-15]

Determinism: same seed -> bit-identical manifest and images.
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import generator as G  # noqa: E402  (public helpers only)

TWIN_CHARS = ["o", "O", "c", "C", "s", "S"]
N_ITEMS = 200           # 100 clean + 100 strike
VARIANTS = ["clean", "strike"]


def twin_word(rng: random.Random) -> str:
    """5-8 twin glyphs, random case. Case is the only signal."""
    return "".join(rng.choice(TWIN_CHARS)
                   for _ in range(rng.randint(5, 8)))


def render(variant: str, seed: int, index: int,
           size: tuple[int, int] = (640, 180)):
    """Deterministic (variant, seed, index) -> (image, label, char_boxes).

    Mirrors generator.draw_label placement (same shrink-to-fit + centre
    math) but keeps the font/x/y so per-char truth boxes can be computed
    with textlength advances (the S26/S28 oracle-box construction, same
    method as tools/gen_hard_corpus.advance_char_boxes). The strike line
    does not move ink, so boxes are exact for both variants.
    """
    from PIL import ImageDraw
    v = VARIANTS.index(variant)
    rng = random.Random(seed * 1_000_003 + index * 7 + v)
    label = twin_word(rng)
    W, H = size
    img = G._paper(rng, W, H)
    size_f = rng.randint(26, 40)
    font = G.load_font(rng, size_f)
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if tw > W - 16:
        size_f = max(12, size_f * (W - 16) // tw)
        font = G.load_font(rng, size_f)
        bbox = d.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2 - bbox[0] + rng.randint(-6, 6)
    y = (H - th) // 2 - bbox[1] + rng.randint(-4, 4)
    d.text((x, y), label, font=font, fill=G._ink_color(rng))

    # per-char tight ink boxes (advance method; +1px like S53)
    boxes = []
    for i, ch in enumerate(label):
        adv = x + d.textlength(label[:i], font=font)
        cb = d.textbbox((adv, y), ch, font=font)
        boxes.append([int(cb[0]) - 1, int(cb[2]) + 1,
                      int(cb[1]) - 1, int(cb[3]) + 1])

    if variant == "strike":
        # one thin gray strikethrough through the text band (mid +-
        # jitter), text-width, 1px: a stitch-seam-style line that perturbs
        # height estimation; glyph strokes survive it (quantified in the
        # report: dark-ink px per item, strike vs clean)
        yy = H // 2 + rng.randint(-10, 10)
        x0, x1 = int(W * 0.15), int(W * 0.85)
        d.line([(x0, yy), (x1, yy)], fill=(120, 118, 115), width=1)
    return img, label, boxes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=973)
    ap.add_argument("--out", default="reports/case-corpus/2026-10-15")
    ap.add_argument("--skip-reads", action="store_true",
                    help="build manifest + montage only (no floor reads)")
    args = ap.parse_args()
    if args.seed in (1, 2, 3, 4, 53):
        print("refusing canonical/frozen seed (evaluation-only)", file=sys.stderr)
        return 2

    out = ROOT / args.out
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i in range(N_ITEMS):
        variant = VARIANTS[i // (N_ITEMS // len(VARIANTS))]
        img, label, boxes = render(variant, args.seed, i)
        assert len(boxes) == len(label)
        fn = f"case-{i:04d}.png"
        img.save(img_dir / fn)
        digest = hashlib.sha256((img_dir / fn).read_bytes()).hexdigest()
        rows.append({"id": f"case-{i:04d}", "image": f"images/{fn}",
                     "label": label, "variant": variant,
                     "seed": args.seed, "index": i, "sha256": digest,
                     "char_boxes": boxes})
    manifest = out / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r) + "\n" for r in rows))
    mhash = hashlib.sha256(manifest.read_bytes()).hexdigest()

    # montage: first 4 of each variant, 2 cols x 4 rows
    from PIL import Image
    picks = [rows[i] for i in list(range(4)) + list(range(100, 104))]
    cell_w, cell_h, pad = 640, 90, 8
    montage = Image.new("RGB", (2 * cell_w + 3 * pad,
                                4 * cell_h + 5 * pad), (245, 243, 240))
    for k, r in enumerate(picks):
        im = Image.open(img_dir / Path(r["image"]).name)
        im.thumbnail((cell_w, cell_h))
        x = pad + (k % 2) * (cell_w + pad)
        y = pad + (k // 2) * (cell_h + pad)
        montage.paste(im, (x, y))
    montage.save(out / "montage.png")

    import numpy as np
    from PIL import Image as _Im
    ink_stats = {}
    for variant in VARIANTS:
        dark = []
        for r in (x for x in rows if x["variant"] == variant):
            g = np.asarray(_Im.open(img_dir / Path(r["image"]).name)
                           .convert("L"))
            dark.append(int((g < 100).sum()))
        ink_stats[variant] = {"dark_ink_px_median": int(np.median(dark)),
                              "dark_ink_px_min": int(min(dark)),
                              "dark_ink_px_max": int(max(dark))}
    glyphs = sum(len(r["label"]) for r in rows)
    print(f"corpus: {len(rows)} items ({N_ITEMS // 2} clean + "
          f"{N_ITEMS // 2} strike), seed {args.seed}, "
          f"{glyphs} labeled twin-glyph case decisions")
    print(f"dark-ink px per item: {ink_stats}")
    print(f"manifest sha256: {mhash}")
    print(f"regen: python3 tools/s73_case_twin_corpus.py --seed {args.seed} "
          f"--out {args.out}")

    if not args.skip_reads:
        import baseline as B
        base_rows = []
        for r in rows:
            img = Image.open(out / r["image"]).convert("RGB")
            got, _ = B.read_text(img, None)
            base_rows.append({**{k: r[k] for k in ("id", "variant", "label")},
                              "got": got,
                              "exact": got == r["label"],
                              "exact_case_insensitive":
                                  got.lower() == r["label"].lower()})
        (out / "floor_rows.json").write_text(json.dumps(
            {"reader": "plain floor (baseline.read_text)",
             "seed": args.seed, "rows": base_rows}, indent=1) + "\n")
        for variant in VARIANTS:
            vr = [r for r in base_rows if r["variant"] == variant]
            ex = sum(r["exact"] for r in vr)
            ci = sum(r["exact_case_insensitive"] for r in vr)
            print(f"  {variant:7s} case-exact {ex:3d}/{len(vr)}   "
                  f"case-insensitive {ci:3d}/{len(vr)}")
    print(f"out: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
