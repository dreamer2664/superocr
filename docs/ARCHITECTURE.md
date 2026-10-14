# ARCHITECTURE — how superocr is put together

_Map of the stack for newcomers (and for Carlo). Every number quoted here cites a
committed receipt; if a receipt is missing, the claim is marked as such. Last
verified against main @ `a530a8f` (2026-10-13)._

## The one-paragraph version

`generator.py` deterministically renders word images (easy: clean text; hard:
degraded — collage, corrosion, cross-shadow, darts, spiderweb, strippy, split,
stitch, obstruction, dark-on-dark, many fonts). `bench.py` scores any reader
against the two canonical suites and writes timestamped receipts. The shipping
reader is the **floor pipeline** (`baseline.read_text` → optional R5 rescue →
optional lexicon fix), currently at **easy 73/100, hard 23/100** on seed-1 —
measured, three consecutive runs, not asserted. Parallel to it sits a **CNN lane**
(`readers/glyphcnn.py` + `models/glyphcnn-v*.npz`) trained on the S53 hard
corpus; v7b reaches crop-level top-1 0.7998 but is **not yet wired into the
shipping path** (integration is task t-20261013-becc). The bar (easy ≥98, hard
≥95, ×3 runs, demo ≤10 s median, clean-clone) is **not met**; see
[DECISIONS.md](DECISIONS.md) for the full state.

```
                 ┌────────────┐   seeds, fonts    ┌──────────────┐
                 │ generator  │ ────────────────▶ │ suites        │
                 │ (determin.)│                   │ easy/ hard/   │
                 └────────────┘                   │ manifest+imgs │
                                                  └──────┬───────┘
                                    dir-hash verified    │
        ┌────────────────────────────────────────────────┤
        ▼                                                ▼
┌───────────────┐  read_text(img, None)          ┌───────────────┐
│ FLOOR (ships) │  → (text, confs)               │ bench.py      │
│ baseline.py   │                                │ (the judge)   │
│  + R5 rescue  │                                │  writes       │
│  + lex fix ───┼── tools/lex_projection.fix_line│  reports/*.json│
└───────────────┘                                └───────┬───────┘
        ▲                                                ▼
┌───────────────┐                                ┌───────────────┐
│ CNN lane      │  crop-level, offline           │ validate_     │
│ glyphcnn v4/  │  (not shipping yet)            │ report.py     │
│ v7/v7b + S53  │                                │ --strict      │
│ hard corpus   │                                │ (4 stamps)    │
└───────────────┘                                └───────────────┘

Delivery: webapp/ (local server + browser UI, lex route)
          app/build_bundle.py → downloadable zip + GitHub Release (PR #71)
```

## Modules, one line each

| path | what it is |
|---|---|
| `generator.py` | Deterministic image+label generator. `G.generate_one(family, seed, index)`; fonts resolve system-first with bundled fallback (`G.available_fonts()`) — on machines without the expected faces it must fail loud, never silently degrade to Pillow's bitmap default. |
| `typer.py` | The "AUTO" reader mode + family typing; `T.recognise(img, family)`. |
| `preclassify.py` | Cheap family pre-classifier (centroids in `models/preclass_centroids.npz`). |
| `baseline.py` | **The floor.** `baseline.read_text(img, None) -> (text, confs)` — segmentation + template matching. This is the shipping reader's core. |
| `reader.py` | Reader plumbing/compat layer around baseline. |
| `readers/` | CNN lane: `glyphcnn.py` (crop classifier), `cnn_reader.py`, `piece_cnn.py`, `segmentation.py`. |
| `models/` | Committed weights: `glyphcnn-v2/v3/v4/v7/v7b.npz`, `preclass_centroids.npz`. Small by design (CPU, stdlib+numpy+Pillow only, no pretrained downloads — repo constraint). |
| `recipes/` | Training recipes per model version, including protocol fields (train/val split, class cap, per-cell baselines) so a reviewer can audit without re-running training. |
| `tools/lex_projection.py` | Lexicon fix: `fix_line(text)` projection scoring over a word list. Shipping lex route = `baseline.read_text` → `fix_line`. |
| `tools/reader_lex.py` | CLI wrapper for one-image reads (`python3 tools/reader_lex.py {image}`) — byte semantics verified against the settled receipts. |
| `tools/make_suites.py` | Regenerates the suites from `generator.py`, deterministically; `--check` verifies. |
| `bench.py` | **The judge.** Scores any reader; `--runs 3` for stability; writes `reports/<ts>-<suites>.{json,md}` + gallery. Contract in [BENCH.md](../BENCH.md). |
| `tools/validate_report.py` | Reviewer-side reproducibility gate: `--strict --data <suite-dir>` re-checks the four stamps (dir hash, reader identity, scorer, env). A bench report without the stamps is refused. |
| `tools/s30_v7_read_probe.py` | Read-level probe for CNN arms against canonical suites, with gated OFF control (S51 pattern: the OFF arm must reproduce the settled line or the probe is void). |
| `tools/gen_hard_corpus.py` | S53 hard-corpus generator (2000 items; train 0–1599 / val 1600–1999). |
| `webapp/server.py` | Local HTTP server (`--port`, `--host`, `--suites`, `--selftest`); `/api/ocr` with `route=lex`, `/api/health` reports fonts + git commit. Dev port 8421, bundle port 8477. |
| `webapp/static/` | Browser UI: gallery, read-an-image, **Share screen** (`getDisplayMedia` — fixed in PR #71; it used to call `getUserMedia`, i.e. the camera). |
| `app/build_bundle.py` | (PR #71) Builds the downloadable standalone zip: launchers with deps-check, selftest against build-time expected reads, auto-restart watchdog, bundled fonts, INSTALL.md. Output is a GitHub **Release asset**, never committed. |
| `tests/` | Offline, fast-ish, seeded. Full suite ≈9 min and wants ≥2 GB free RAM (learned the hard way: running it concurrently with servers on a 2 GB box thrashes the machine). |

## Data + receipts conventions

- **Suites**: `easy/` + `hard/`, 100 items each, `manifest.jsonl` with per-item
  `label` (the expected-text field is called `label`) and `image` (relative to the
  manifest's directory). Canonical seed-1 dir-hash prefix `b2c460d2fb5a`;
  seed-2 (independent generalization screen) `ec64cd63790d8824`. Always verify the
  dir hash before quoting a number from a suite you regenerated.
- **Reports**: `reports/<UTC-timestamp>-<suite>.json` + `.md`; the JSON carries
  `doc['suites'][suite]` with `correct/pct/bar/median_s/p95_s/failures/results`
  per suite — that is the structure `validate_report.py` and every reviewer script
  consume.
- **Every claim cites a receipt.** Numbers in PRs, on the bus, or in these docs
  must point at a committed receipt path (or an open PR branch + sha). Selection
  effect and winner's curse are real: clean-item accuracy does not transfer, and
  held-out seeds must be validated before shipping (S38 exists for exactly this).

## Where the key numbers live (as of a530a8f + open PRs)

| number | value | receipt |
|---|---|---|
| Shipping line, seed-1 | easy 73/100, hard 23/100, ×3 consecutive | `reports/s22-3x-settled/20261013T101654Z-{easy,hard}.json` — on PR #53's frozen branch (`584f8c4`), not yet in main |
| Shipping line, seed-2 | easy 74, hard 29 | `reports/s38-seed2-fresh/20261013T133120Z-easy-hard.json` (merged, #68) |
| Hard-miss census | 77 misses = 63 segmentation / 9 case / 5 glyph; lex helped 17, hurt 0 | `reports/s43_failure_analysis.{md,json}` (merged, #69) |
| CNN v7b crop-level | TOTAL 0.4334 → 0.7998 vs v4; rotation arm 0.85–0.96 without de-rotation | `reports/s30-v7b/per-severity.json` (merged, #67) |
| CNN v7b read-level (floor segmentation) | easy glyph 0.9009 → 0.9235, exact 19 → 31; hard glyph 0.7908 → 0.8095, exact 6 → 7 | `reports/s30-v7b/read-probe.json` (merged, #67); independently reproduced byte-for-byte by a reviewer on the canonical suite |
| S53 hard corpus | 2000 items, manifest sha `44b79be7ea90551a…`, per-item rng `sha256("s53-hard:53:{index}")` | `reports/s53-hard-corpus/report.md` (merged, #66) |
| CLAHE pre-step | net-harmful (hard 23→20→18), NO-SHIP | `reports/s51-clahe.md` + 600 committed rows (PR #70) |
| Standalone app | selftest 12/12 clean-room, warm lex ≈0.9 s | `reports/app-bundle.md` (PR #71 branch `872cac7`) |
| Text layer (iris_lex v1.2) | easy 98 once (needs ×3), hard ≈87 | external lane — not in this repo; quoted from bus receipts |
