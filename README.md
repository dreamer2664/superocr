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

### easy (t-ec08)

`easy` is registered alongside the hard families in the same CLI: plain text,
uniform clean background, faces/sizes 16-48, mixed case + digits, exact
labels. Its suite targets >=98/100. This branch stacks on the e071 branch
(generator.py does not exist on main yet); when #1 lands, retarget to main.

### reader.py — S3 war one (t-20261011-2ca7)

Classic (no ML) readers for `obstruction` and `dark-on-dark`:
high-pass residual vs a wide Gaussian (kills vignette and smudge), sigma/p99
anchored threshold, despeck, column segmentation, wide-blob splitting, DejaVu
template matching (IoU + 9x9 density correlation), case-twin height rule,
lexicon rerank. `python3 reader.py img.png --family F` prints the text;
`--score` prints honest exact/char accuracy against the generator manifest.

First truth (reports/2ca7-first-measurement.md, gallery included): char acc
0.44-0.53 obstruction, 0.59-0.65 dark-on-dark, exact-match far below the bar.
The strategies make the families readable; closing the gap is the S1/S2
matcher work. Numbers are published as measured - that is the rule.
