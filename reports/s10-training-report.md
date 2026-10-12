# S10 — training + truth: CNN glyph model v2 (12 Oct 2026)

Task `t-20261012-4447`. Branch `agent/scott/t-20261012-4447`.

**What ships:** `models/glyphcnn-v2.npz` (234552 B), its recipe
`reports/s10-recipe-cnn-v2.json`, and this report. The weights are
**bit-identical** to the model used for the three-run official proof (all 8
arrays `allclose` against `/tmp/s10-D.npz`), so the shipped file and the
shipped number are the same weights; the regen just records the fingerprints
the original run predates.

**What it buys, honestly:** official suite screen 31/100 easy, 8/100 hard,
three consecutive runs identical — against 29/6 for the committed weights.
**The bar (98/95) is not met.** The number below is the number;

## Artifact

| field | value |
|---|---|
| weights | `models/glyphcnn-v2.npz` — 234552 B |
| recipe | `reports/s10-recipe-cnn-v2.json` |
| architecture | conv3x3(8)-pool-conv3x3(16)-pool-fc96-fc62, 24×24 ink-bright crop, 62 classes |
| seed | 11 |
| per-class (flag) | 200 → recipe `per_class` 224 (= `len(y)//62` over the full set) |
| train / val | 11952 / 1961 |
| epochs | 34, 171.1 s |
| final val acc | 0.9225 |
| data fingerprint | `ff8b4357eb4a868a` |
| source fingerprints | generator.py `e160058dfd48`, readers/segmentation.py `04291a2a1069`, tools/train_glyphs.py `f84aee4fdc60` |

Regeneration (deterministic; `nproc=2`, do not run several in parallel):

```bash
python3 tools/train_glyphs.py --per-class 200 --epochs 34 --generator-sheets 400 \
    --data /tmp/s10-data-p200.npz --out /tmp/s10-D-v2.npz
# val acc 0.9225 | data ff8b4357eb4a868a | 234552 bytes
```

Use it anywhere the 8/16 CNN is used today (drop-in, same arch/size):

```bash
python3 readers/cnn_reader.py --image <png> --weights models/glyphcnn-v2.npz
```

## Official suites — screen and proof

Suites `/tmp/s10-suites` (easy 100 + hard 100, seed 1, suite hash
`b2c460d2fb5a`). One-run bench results are a SCREEN, not a shippable number:

| model | easy | hard |
|---|---|---|
| committed `models/glyphcnn.npz` | 29/100 | 6/100 |
| E1 synthetic-only | 20/100 | 7/100 |
| E2 agreement-gated | 29/100 | 6/100 |
| **D = `glyphcnn-v2.npz` (shipped)** | **31/100** | **8/100** |

Three-run proof for the shipped weights (`tools/three_run_proof.py --runs 3`):
**31/100 easy, 8/100 hard, identical in all three runs** — `VERDICT: FAIL`
against the 98/95 bars. Raw reports, per-run galleries and the stability JSON
are in `reports/three-run-20261012T074804Z/`; the 27 MB of run galleries were
kept out of the repo (they are regenerable and would bloat clones) and live at
`/home/user/s10-cnnv2-gallery/`.

## The honest frame: the bar is per-character, not per-item

New: `tools/suite_char_analysis.py` reads a bench report and converts it to
the numbers that actually explain the gap (`reports/s10-char-analysis.json`).

| | easy | hard |
|---|---|---|
| mean label length | 24.3 chars | 22.0 chars |
| bar (whole-string exact) | 98/100 | 95/100 |
| per-char accuracy the bar demands | **99.917 %** | **99.767 %** |
| per-char accuracy measured (D) | **89.3 %** | **34.0 %** |
| measured for committed weights | 89.1 % | 33.2 % |

With 24.3 characters per label, one wrong glyph loses the whole item: even a
99 % per-character reader scores only 0.99^24.3 ≈ 78/100 exact. The easy bar
is a ~1 mistake per 1200 characters budget; we are at roughly one per 9.
This is why "+2 easy" is what a better CNN bought — the item score is a
nonlinear compression of a per-character problem.

Where D's 69 easy failures sit (`reports/s10-char-analysis.json`):

* **11 fail on case only** — every glyph identity is right, the case call is
  wrong. 3 more fail on spacing only. These 14 items (→ 45/100) need no new
  classifier, only a decision layer (this is exactly S8's case-twin work).
* 29 fail within two edits — single-glyph slips, the classifier's real work.
* The rest are multiple slips, often around `r→f`, `n→h/u`, `m`-width and
  5/S/8/0-class confusions; the per-class table in `tools/s10_diagnose.py`
  output names them.

On hard, failures are large (only 4 of 92 within two edits): hard is
segmentation-limited, not glyph-limited — the per-character accuracy collapses
because whole lines are cut or merged, and no classifier change can reach it.

## Experiments behind the number (all on the same fixed split, seed 11)

| run | change | own-val acc | suite screen | read |
|---|---|---|---|---|
| recorded | committed recipe replay at today's main | 0.8998 vs 0.8921 recorded | 29/6 | drift; fixed by fingerprints |
| B | bigger net (597 KB, fc128) | 0.9106 | not run | capacity ≠ suite gain |
| E1 | synthetic-only crops (no harvest) | **0.9251** | **20/7** | best val, worst easy suite |
| E2 | harvest with agreement gate 0.85 | 0.9200 | 29/6 | hygiene, no gain |
| **D** | per-class 200, same arch | 0.9225 | **31/8** | shipped |

**Val does not rank the suites.** E1 has the best val accuracy of any run and
the worst easy-suite score; D is second and wins both. Glyph-level val is a
diagnostic, the official three-run proof is the decision.

**Correction carried here for the record:** the earlier claim that junk crops
"poison" the net was wrong. Misaligned crops do pass the box-count filter, but
the synthetic-only control (E1) reads the harvested val block at 82.9 % — the
same as the harvest-trained run — so ~83-84 % is what harvested crops honestly
hold, and the 96 %+ figure seen elsewhere was train/val overlap. The agreement
gate stays in `tools/train_glyphs.py` as sheet hygiene (`--min-agree`, default
0.85, drop-sheet-never-relabel); it is not a score fix and no val gain is
claimed for it.

## Next levers, in measured order

1. Case + spacing decisions on already-correct glyph streams: 14 easy items of
   headroom with zero classifier change (S8 owns this).
2. Single-glyph slips (29 items within two edits): more/cleaner crops through
   the reader's own segmenter, class-balanced; per-class table already in
   `tools/s10_diagnose.py --json`.
3. Hard stays a segmentation problem until S7's walls move; glyph work does
   not reach it.

## Reproduce

```bash
python3 tools/make_suites.py --easy 100 --hard 100 --seed 1 --out /tmp/s10-suites
python3 tools/three_run_proof.py --runs 3 \
  --reader "python3 readers/cnn_reader.py --image {image} --weights models/glyphcnn-v2.npz" \
  --out /tmp/proof.md
python3 tools/suite_char_analysis.py --report <bench.json>
python3 tools/s10_diagnose.py --data /tmp/s10-data.npz --model models/glyphcnn-v2.npz
```
