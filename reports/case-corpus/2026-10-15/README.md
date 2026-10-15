# S73 — case-twin probe corpus (t-20261014-1759)

Dev/held-out material for the S70 image-side case instrument. Canonical
suites carry only 9 case misses; this corpus isolates case decisions.

## What it is

200 items, every glyph drawn from the x-height twin set {o,O, c,C, s,S}
(same shape, different height — the template matcher's classic confusion
class). 1,276 labeled per-glyph case decisions with truth geometry
(`char_boxes`, advance-method, +1px, same construction as the S53
corpus). Two variants, 100 items each:

- **clean** — plain render, no degradation. The x-height cue is fully
  available: the honest upper bound for an image-side instrument.
- **strike** — same render + one 1px gray strikethrough through the
  text band (stitch-seam style). Glyph strokes survive it (dark-ink px
  per item, median 884 strike vs 893 clean — the line perturbs height
  estimation, not the letters).

Frozen identity: seed 973, `manifest.jsonl` sha256
**baec4fbd61581a9787c0443eab8962a5fd6455d2a84711529a8579896185ae7f**
(bit-identical across regenerations — verified). Regenerate:

```bash
python3 tools/s73_case_twin_corpus.py --seed 973 --out reports/case-corpus/2026-10-15
```

Images are generated, not committed (`images/` is gitignored); the
committed identity is the manifest + hash + tool. Canonical recipes
untouched (generator helpers used as-is; no suite hash can move).

## Plain-floor baseline (floor_rows.json)

| variant | case-exact | case-insensitive |
|---|---|---|
| clean | 75/100 | 81/100 |
| strike | 0/100 | 0/100 |

Readings for S70:

- On **clean** twins the floor resolves case surprisingly often (75%)
  but 19 items still carry letter errors and 6 are case-only misses —
  per-glyph case-decision scoring (the 1,276 labeled decisions) is the
  right unit, not word-exact.
- On **strike** the floor reads nothing (0/100, case-insensitive too):
  the line fuses its segmentation path. The strike arm is therefore
  **instrument-only stress material** — S70 should use truth
  `char_boxes` (dev) for it, per the S56 contract pattern; glyph ink
  is intact and a human reads the words fine.
- No 98/95 claim is made or implied; this is probe material, not a
  bench. Montage: `montage.png` (4 clean + 4 strike).
