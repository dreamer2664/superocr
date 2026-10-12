# superocr

Reads the words out of difficult pictures — striped, split, snowy, shadowed
images — and hands you the text.

**Honest status, one line:** it runs end to end and fast (every image read in
under five seconds), but it does not yet read accurately (3 of 100 clean images read
exactly right; the target is 98). The plumbing is done; the accuracy is the
work in progress. Everything described below works today.

---

## What you need (five minutes, once)

1. **Python 3** — open a terminal and type `python3 --version`.
   If that prints something like `Python 3.10.x`, you're set; if it says
   "command not found", install Python from python.org (or your app store).
2. **Two free add-ons** — in that same terminal:
   ```
   python3 -m pip install numpy pillow
   ```
   (if it refuses with a permissions error, try
   `python3 -m pip install --user numpy pillow`)
3. **This folder** — on GitHub press the green **Code** button →
   **Download ZIP**, then unzip it. Or, if you use git:
   `git clone https://github.com/dreamer2664/superocr`

All commands below are typed in a terminal, from inside this folder.

## Try it (two minutes)

Make a practice picture:

```
python3 generator.py --family easy --count 1 --seed 7 --out practice
```

You now have `practice/easy_000.png` — a clean image with a few words in it.
The true words are written down in `practice/manifest.jsonl` (open it with any
text editor), so you can check the answer.

Read it:

```
python3 typer.py practice/easy_000.png
```

This prints the text the program saw, and which of the 13 image styles it
decided this was. It will be *close* but not perfect — that is the honest
status above. Try harder pictures too:

```
python3 generator.py --family strippy --count 3 --seed 15 --out practice
python3 typer.py practice/strippy_000.png
```

## Watch it work in your browser

```
python3 tools/demo_server.py --port 8420
```

Now open **http://localhost:8420** in your browser. Drag any picture onto the
big dashed box (the ones you made in `practice/` work fine), leave *family*
on **auto**, and press **read it**. You'll see the text it read, the style it
detected, and how long that took. To stop the server, click the terminal and
press **Ctrl+C**.

To measure the speed honestly (it runs the demo for you and prints a table):

```
python3 tools/demo_latency.py --repeats 3
```

Every line should end in `[ok]` — each read under 10 seconds; in practice
between a quarter of a second and about four.

## Read your own picture

```
python3 typer.py /path/to/your-image.png
```

- The text is printed in the terminal (that's the default).
- To save it to a file instead: add `--target file:answer.txt`
- To read just one rectangle of a big screenshot (useful for a single form
  field): add `--crop 800x200+40+30` — that's width 800, height 200, starting
  40 from the left and 30 from the top.

**Where this may and may not be used.** It types what it *thinks* it sees
into a field you aimed it at — notes, forms, search boxes. Never wire it into
password prompts, payment or transfer confirmations, medical or legal entry,
or anything that *acts* on what it types. It is a transcription convenience,
not an automation authority.

## Check everything still works

After downloading a new copy or updating, run the test suite:

```
python3 tests/run_all.py
```

The last line should end in **files passed** with no failures (16 test
files at the time of writing; it takes a few minutes).

## Score it yourself (the honest score card)

```
python3 tools/make_suites.py
```

Builds the two official test sets inside `data/` — 100 clean images and 100
deliberately-hard ones (takes about a minute, same images every time).

```
python3 bench.py --reader "python3 tools/bench_adapter.py {image}"
```

Grades the reader against them (about three minutes) and writes a report into
`reports/`, including a *gallery* folder with every image it got wrong, so
you can see the failures rather than take our word for them.

As measured on 12 October 2026 (seed 1, on main 9a3c6f4, re-screened after the S9
merge): **easy 3/100, hard 2/100** exact matches — bars are 98 and 95, so **not met**.
The floor to beat is `baseline.py` at 28/9, and the best merged reader (CNN v2) screens
31/8; the full four-path table lives in `reports/s11-official-screens.md`. The numbers are whatever these
commands print on the day you run them; nothing is rounded up.

## The 13 image styles ("families")

`easy` plain text on a clean background · `snow` speckled noise ·
`spiderweb` web strands · `split` image sheared in two · `stitch` two strips
sewn together · `strippy` horizontal bands over the text · `cut` letters
sliced by thin slashes · `collage` different background per region ·
`corrosion` blotchy stains · `cross-shadow` a shadow edge across the image ·
`darts` scattered darts · `obstruction` a solid bar in front of the text ·
`dark-on-dark` text barely lighter than the background.

You normally don't pick — `auto` looks at the image, decides the family
itself (that is what makes it fast), and reads it with that family's method.

## If something goes wrong

| You see | Meaning / fix |
|---|---|
| `python3: command not found` | Python isn't installed — see step 1 above |
| `ModuleNotFoundError: No module named 'numpy'` | Re-run the install line in step 2 |
| `bench: --reader is required` | Copy the bench line exactly, quotes included |
| `Address already in use` when starting the demo | Another server holds that port — use `--port 8421` |
| A read is complete garbage | If the image style is unusual, try `--family <one of the 13 above>` to pin it — but do report it; failures drive the work |

---

# For engineers (project log)

**This folder is a read-only mirror.** The project's real home — code,
branches, pull requests, demo — is
**https://github.com/dreamer2664/superocr**; this copy exists so the group's
board, bus and reviews can see it without cloning. **Never edit here by
hand**: the next mirror run replaces the folder. Heavy artefacts (models,
generated datasets) are deliberately not mirrored — except
`models/preclass_centroids.npz`, the tiny (a few KB) committed cache that
lets auto mode start instantly; `python3 preclassify.py --rebuild`
regenerates it deterministically.

The bar, the honesty rule and the branch plan: [JOBS.md](JOBS.md).
Reference sheets from Carlo (the kinds of images that must be read) are in
`reference/`.

## generator.py — the hard families (t-20261011-e071, marcus-aurelius)

Twelve seeded generators, one function per hard family: snow, spiderweb,
split, stitch, strippy, cut, collage, corrosion, cross-shadow, darts,
obstruction, dark-on-dark. Each returns `(PIL.Image, label)` where the label
is the exact case-sensitive ground truth. stdlib + numpy + Pillow only.

```
python3 generator.py --list
python3 generator.py --family snow --count 8 --seed 42 --out out/hard_snow
python3 generator.py --family all --count 2 --seed 7 --out out/hard_all
```

`--out` writes PNGs plus `manifest.jsonl` (one JSON line per image:
file/label/family/seed/index) — the format the bench (t-2f3d) consumes.
`samples/hard/` holds a 12-image seeded preview with its own manifest.

Determinism: every stream of randomness derives from
`sha256(f"{family}:{seed}:{index}")`; same seed → byte-identical PNGs on the
same fonts/FreeType. Fonts: DejaVu faces at `/usr/share/fonts/truetype/dejavu/`
(standard on ubuntu CI); when absent, the code falls back to Pillow's bundled
face with a note, so the suite still runs.

Honesty notes: labels never contain look-alike traps by design —
confusability is the reader's problem; `dark-on-dark` is adversarial by
design (background 8-22, ink +14..30 luminance); its difficulty is the point.
`samples/hard/` previews are JPEGs; exact datasets are generated, never
committed.

## reader.py — classic readers and the chain (t-2ca7, t-407f, t-d1a6)

Classic (no ML) readers: high-pass residual vs wide Gaussian, sigma/p99
anchored threshold, despeck, column segmentation, wide-blob splitting,
DejaVu template matching (IoU + 9x9 density correlation), case-twin height
rule, lexicon rerank. Structural repairs for split (row-profile (cut, dy)
search), stitch (seam-colour strip alignment), strippy (loose luminance
cut), cut (vertical closing). `read_chain()` / `--chain`: P1 match; low-conf
glyphs retry P2/P3; gated P4 lexicon rerank.

First truths (galleries included, all below the bar): char acc 0.44-0.65
across the families, exact far below — `reports/2ca7-*`, `reports/407f-*`,
`reports/d1a6-*`. The matcher is the ceiling; S10 lifts it.

## preclassify.py + auto mode (t-20261012-5c63)

Auto used to run all 13 family chains and pick by average glyph confidence:
8-21 s per image, and the arbitration was gameable — garbage glyphs decoded
confidently beat the right chain (an easy image was regularly read as
'cut': 32/104 correct-family picks vs 84/104 for trusting the
pre-classifier). Now `preclassify.py` looks first: 21 structural numpy
features (contrast, speckle, stripe periodicity, seam sharpness, halves
offset, banding, blotch energy...), nearest-centroid over seeded generator
samples. Held-out truth: top-1 87%, top-2 94%. `typer.recognise(auto)` runs
that ONE chain; only a failed read (fewer than 3 glyphs) walks down the
ranking — bounded, worst case all 13.

```
python3 preclassify.py image.png          # ranked families
python3 preclassify.py image.png --top 3
python3 preclassify.py --rebuild          # regenerate the centroid cache
```

`tests/test_preclassify.py` holds the floors: held-out top-2 ≥ 90%, cache ==
rebuild, auto == pinned on the demo probes, per-family auto latency < 10 s.

## typer.py — image to a target field (t-20261011-7b9f)

Targets are opt-in and explicit: stdout (default), file:PATH, xdo (xdotool),
clipboard (xclip/pbcopy). Missing tools produce a plain error offering the
safe targets — never a silent failure. `--crop WxH+X+Y` slices files;
screen capture itself stays external (grim/import/gnome-screenshot), no
hidden grabbing. The full safety rule is the box in the non-programmer
section above.

## Browser demo with measured latency (S4 t-27bc, S9 t-5c63)

```
python3 tools/demo_server.py --port 8420   # open http://localhost:8420
python3 tools/demo_latency.py --repeats 3
```

Single-file page + stdlib server; POST /ocr runs the SAME pipeline as the CLI
(typer.recognise → preclassify → reader.read_chain). Latency is measured,
not promised — and since t-5c63 the bar is **every auto probe** under 10 s,
not the pooled median. Measured 2026-10-12 on main f9cbd91 (--repeats 3): worst probe
median 4.08 s (strippy), overall median 0.77 s — was 26 s on strippy and
12.4 s on split before the pre-classifier. Full breakdown in
`reports/demo-latency.json`.
