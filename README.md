# superocr

Read hard images exactly (case-sensitive), then put the text where it belongs.

**This folder is a read-only mirror.** The project's real home - code, branches,
pull requests, demo - is **https://github.com/dreamer2664/superocr**; this copy
exists so the group's board, bus and reviews can see it without cloning.
**Never edit here by hand**: the next mirror run replaces the folder. Heavy
artefacts (models, generated datasets) are deliberately not mirrored.

The bar, the honesty rule and the branch plan: [JOBS.md](JOBS.md).
Reference sheets from Carlo (the kinds of images that must be read) are in
`reference/`.

## generator.py — the hard families (t-20261011-e071, marcus-aurelius)

Twelve seeded generators, one function per hard family in JOBS.md:
snow, spiderweb, split, stitch, strippy, cut, collage, corrosion,
cross-shadow, darts, obstruction, dark-on-dark. Each returns
`(PIL.Image, label)` where the label is the exact case-sensitive ground
truth. stdlib + numpy + Pillow only.

```
python3 generator.py --list
python3 generator.py --family snow   --count 8 --seed 42 --out out/hard_snow
python3 generator.py --family all    --count 2 --seed 7  --out out/hard_all
```

`--out` writes PNGs plus `manifest.jsonl` (one JSON line per image:
file/label/family/seed/index) — the format the bench (t-2f3d) consumes.
`samples/hard/` holds a 12-image seeded preview with its own manifest.

Determinism: every stream of randomness derives from
`sha256(f"{family}:{seed}:{index}")`; same seed → byte-identical PNGs on the
same fonts/FreeType. Fonts: DejaVu faces at `/usr/share/fonts/truetype/dejavu/`
(standard on ubuntu CI) — eight faces for "many fonts"; when absent, the code
falls back to Pillow's bundled face with a note, so the suite still runs.

The easy family (t-ec08) is a sibling task: add one function and register it
in `FAMILIES`; CLI and tests pick it up unchanged.

Honesty notes (see JOBS.md): labels never contain look-alike traps by design —
confusability is the reader's problem; `dark-on-dark` is adversarial by design
(a handful of luminance steps: background 8-22, ink +14..30); its difficulty is
the point, not a defect. `samples/hard/` previews are JPEGs; exact datasets are
generated, never committed.
