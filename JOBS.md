# superocr — the plan

**The bar (Carlo, 11 Oct 2026).** Read hard images exactly, case-sensitive, then
put the text where it belongs. Measured, not asserted:

| suite | what it is | required |
|---|---|---|
| easy | plain text, clean background | **≥ 98/100** |
| hard | distortion, snow / spiderweb / split / stitch / strippy / cut / collage / corrosion / cross-shadow / darts patterns, semi-transparent obstruction, dark-on-dark, many fonts, several words | **≥ 95/100** |

- **Three consecutive runs** must each clear the bar — stability is part of it.
- **Live demo:** image (a file, or a screen region) → typed into a text box,
  median ≤ 10 s end to end.
- **Reproducible from a clean clone:** seeds, commands and the run report are
  committed. Every number in the README links to a report file.

**The honesty rule (do not bend this).** Some hard families will resist: these
reference images are adversarial by design. A report that says "92/100 on
spiderweb, here is the failure gallery, here is what we tried" is a **good**
report. A report that rounds a number up, or quietly drops a family from the
count, is a failed task. We publish what is true.

## Branches

Work is split so five agents can run in parallel without colliding. Each branch
is a separate task group; within a branch, tasks are sequential where noted.

**S0 — the judge before the player** *(must land first; everything else measures
against it)*
1. `bench.py`: suites (easy/hard), runner, scoring, report writer, failure
   gallery, `--runs 3` stability check. Any reader can be scored by plugging in
   one command-line callable.
2. `generator.py`: the **easy** family — plain text, clean background, many
   fonts/sizes, mixed case + digits, exact labels.
3. `generator.py`: the **hard** families — one function per family named in the
   table above, each producing image + exact label, seeded and reproducible.
4. **Reference pack**: Carlo's four uploaded sheets are committed under
   `reference/`, tiled; the agents label every tile they can read with certainty
   (uncertain tiles are marked `?` and excluded from scoring, never guessed).

**S1 — classic reader (baseline, no ML)**
5. Preprocess + segment + match: contrast normalisation, deskew, per-glyph
   isolation, template matching over rendered fonts. Honest baseline numbers —
   this is what "classic OCR" gets, and the floor for S2 to beat.

**S2 — learned reader (from scratch)**
6. A small per-glyph CNN trained only on data from `generator.py` (CPU-sized;
   weights committed if < 10 MB, else a training recipe + seed).
7. Confidence + fallback: low-confidence glyphs trigger a second pass
   (different preprocessing / larger model / whole-word rerank). The chain is
   instrumented so every improvement is attributable.

**S3 — the hard families, one war each**
8. Obstruction & dark-on-dark: semi-transparent overlays, letters on dark
   backgrounds. (Denoise, channel separation, inversion strategies.)
9. Structure tricks: split, stitch, strippy lines, cut letters — reconnection,
   line removal, deskew. (Two tasks because these need different tooling.)

**S4 — the actual product: "pastes it into a text box"**
10. The typer: a file or screen region → recognised text typed into a target
    field (desktop, opt-in, with a clear README about where this must and must
    not be used).
11. Browser demo: drop an image, see the text + confidence + latency, measured
    on a mid-range phone.

**S5 — proof**
12. Reports: `reports/` gains the three-consecutive-run proof, the README
    numbers, and the failure gallery (the ugly ones included).

**S6 — stretch (only if the bar is not met)**
13. Ensemble, augmentation search, self-training on unlabelled hard images.

## Conventions

- Python 3.11, stdlib + numpy/Pillow only (CPU, no pretrained model downloads).
- Tests offline, fast, seeded; CI runs the suite on every push.
- Heavy artefacts (datasets) are **generated**, not committed.
- Coordination: tasks, votes and discussion live on the chatcode board/bus.
