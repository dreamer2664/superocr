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

### reader.py — S3 structural repairs (t-20261011-407f)

split: (cut, dy) search by row-profile correlation, roll the half back.
stitch: seam-colour columns bound the strips; each strip rolled to align.
strippy: loose luminance cut (<=220) recovers stripe-attenuated ink (paper
never drops below 225), small closing for opaque bands. cut: vertical
closing bridges the slashes. First truth: reports/407f-first-measurement.md
(char 0.45-0.51 split, 0.42-0.49 stitch, 0.26-0.36 strippy, 0.30-0.31 cut)
with gallery. Structure recovered; matcher remains the bottleneck.

### reader.py — confidence + fallback chain (t-20261011-d1a6)

`read_chain()` / `--chain`: P1 match; low-conf glyphs retry P2 (different
preprocessing) and P3 (h=40 templates); shaky words get gated P4 lexicon
rerank. Instrumented per stage. reports/d1a6-chain-measurement.md: the one
clean gain is the P4 gate (obstruction char 0.56 -> 0.60); the passes
themselves do not move the bar - the matcher is the ceiling, S1/S2 lift it.

### typer.py — S4 product: image to a target field (t-20261011-7b9f)

Targets are opt-in and explicit: stdout (default), file:PATH, xdo (xdotool),
clipboard (xclip/pbcopy). Missing tools produce a plain error offering the
safe targets - never a silent failure. --crop WxH+X+Y slices screen-capture
files; capture itself stays external (grim/import/gnome-screenshot), no
hidden screen grabbing. 4 checks green.

WHERE THIS MAY AND MAY NOT BE USED: the typer types into a field the user
aimed it at - notes, forms, search boxes, their own tools. NEVER wire it
into password prompts, payment or transfer confirmations, medical/legal
entry, or anything that ACTS on what it types. It is a transcription
convenience, not an automation authority; recognised text carries the
reader's confidence, and the reader is below the bar until S1/S2 land.

## Browser demo with measured latency (S4, t-20261011-27bc)

    python3 tools/demo_server.py --port 8420   # open http://localhost:8420

Single-file HTML page + stdlib server; POST /ocr runs the SAME pipeline
as the CLI typer (typer.recognise -> reader.read_chain). Latency is
measured, not promised:

    python3 tools/demo_latency.py --repeats 7

Overall median 7.1 s (bar 10 s, MET on the measuring box — localhost,
no phone in the loop; see "Where this was measured" in
reports/demo-latency.md) with the full breakdown in
reports/demo-latency.md — including the families that exceed the bar in
auto mode and why (auto runs every family chain; pin the family to skip
the slow ones: easy image, 661 ms pinned).
