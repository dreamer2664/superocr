# S53 — the hard corpus: 2000 severity-controlled degraded images (t-20261013-4c7b)

**Why.** S29/S30 measured the retrain lane's wall: augmentation flags move
corroded glyph identity +14/+15 (v4) but plateau (de-rotated stuck ~0.70
across v3/v4/v5), and the v6 diagnostic located the plateau in inter-glyph
contamination — solo-crop training never sees read-time crop semantics.
Pericles/Carlo's call: the CNN needs MORE hard data with controlled
difficulty, not more flags. This corpus is that data.

**What.** `tools/gen_hard_corpus.py` — the canonical `generator.py` recipes
are imported UNTOUCHED (official suite hash b2c460d2fb5a re-verified after
generation); the degradation MECHANICS are parameterized around severity:

| arm | severities | mechanic (canonical = the fam_* range) | n |
|---|---|---|---|
| corrosion | light / medium / heavy / extreme | 70-130 / **140-260 (canonical)** / 210-390 / 350-650 pits, r 1-3, bg patches, median-3 | 446 |
| rotation | mild ±2 / moderate ±5 / severe ±9 (=collage) / extreme ±14 | full-sheet BICUBIC, expand | 444 |
| overlay | spiderweb / cross-shadow / strippy / darts × light / heavy | count/alpha/strength scaled; heavy = canonical ranges | 888 |
| combined | 2-3 stacked degradations, random severities | rotation applied last (ink coordinates stay computable) | 111 |
| control | none | undegraded label renders (the contrast arm) | 111 |

- **2000/2000 items carry per-char ground-truth boxes** (`char_boxes`),
  advance-based (textlength) — exact even when glyphs touch; rotation
  transformed. This is the v6 lesson operationalized: the retrain can cut
  word-context crops with read-time semantics (neighbour edges included).
- Deterministic: per-item rng = sha256("s53-hard:{seed}:{index}"), seed 53.
  Manifest sha256: **44b79be7ea90551a** (first 16 hex).
- Suite-format manifest (`id, image, label, family, tags`) plus
  `degradation_type, severity, rotation_deg, char_boxes`.
- **Generated, not committed** (JOBS.md; 191MB): regenerate bit-identical
  with `python3 tools/gen_hard_corpus.py --count 2000 --seed 53 --out corpus/hard2000`.
  A 12-image review sample with index is committed under
  `reports/s53-hard-corpus/sample/`.

## The severity gradient (receipt)

Reader: the shipping route (`tools/reader_lex.py`), 12 sampled items per
cell, seed-7 sample draw:

| cell | exact |
|---|---|
| control (undegraded) | **8/12 = 66.7%** |
| corrosion / light | 3/12 = 25.0% |
| corrosion / medium (= canonical pit range) | 0/12 = 0.0% |
| corrosion / heavy | 0/12 = 0.0% |
| corrosion / extreme | 0/12 = 0.0% |
| rotation / mild (±2°) | 7/12 = 58.3% |
| rotation / moderate (±5°) | 6/12 = 50.0% |
| rotation / severe (±9°) | 10/12 = 83.3% |
| rotation / extreme (±14°) | 8/12 = 66.7% |
| overlay / light | 1/12 = 8.3% |
| overlay / heavy | 1/12 = 8.3% |
| combined (2-3 stacked) | 0/12 = 0.0% |

Readings (n=12, so treat small gaps as noise):

- **Corrosion is a clean difficulty dial**: 67% → 25% → 0%. Medium starts
  at the canonical pit range (140-260) and the 0/12 matches the official
  suite's corrosion 0/8 — the dial is anchored to canonical difficulty.
  Light (70-130 pits) is the first genuinely-trainable hard band we've
  measured.
- **Overlays collapse the reader immediately** (8.3% at light). The
  overlay arms are where retraining should pay hardest.
- **Uniform whole-sheet rotation is NOT the killer we assumed** — 50-83%
  across severities with no monotonic drop (cells overlap within noise).
  The canonical collage family's lethality must come from per-word
  differential rotation + patchwork, not the angles per se. Correcting an
  earlier claim in this thread: rotation cells first measured 0/12, which
  was a generator artifact — PIL's `rotate(expand=True)` default fill is
  black, stamping four huge black triangles on the sheet (up to 28%
  near-black pixels). Fixed by filling with the border-median paper
  colour; corrosion/overlay/control arms verified bit-identical across
  the fix, manifest sha unchanged (angles/boxes identical).
- **Combined (2-3 stacked degradations) is 0/12** — the genuinely-fatal
  band for curriculum endpoints.

The gradient is the point: difficulty is a dial now, so the retrain can
curriculum-scale (light → extreme) and the benchmark can measure
per-severity progress instead of a single 0/8 family number.

## Use

- **Retrain (S30 continuation / v7)**: crops cut at `char_boxes` with
  word-context semantics; severity labels enable curriculum training
  (light → extreme) and per-severity evaluation.
- **Benchmarking**: 2000 items vs the canonical 100 — per-severity
  sensitivity curves for any reader, not just ours.

## Held-out protocol (binding for any S30/v7 use of this corpus)

Per marcus's review note on the task (winner's-curse lesson from
S28/S29: v3-on-dead-families and v4-rotation-transfer both looked fine
in-train and died held-out):

1. **Canonical suites NEVER enter training data** — seed 1/seed 2
   canonical items are evaluation-only, forever.
2. **This corpus is seed 53; do not validate on it if you train on all of
   it.** Split by index before any training run: train 0-1599,
   val 1600-1999 (or generate a separate seed for validation — the
   generator is deterministic per-seed).
3. Report corpus-val AND canonical hard/easy numbers for any retrain;
   a retrain that only improves corpus-val is suspect.
4. Volume is not realism (S42's point, agreed): this corpus is the
   controlled-difficulty substrate, not a substitute for more realistic
   degradation families. The two lanes compose.

## Files

- `tools/gen_hard_corpus.py` — the generator (deterministic, hash-safe)
- `reports/s53-hard-corpus/gradient.json` + this report — the receipt
- `reports/s53-hard-corpus/sample/` — 12-image review gallery + index
- `corpus/hard2000/` — generated locally, gitignored, manifest sha256 above
