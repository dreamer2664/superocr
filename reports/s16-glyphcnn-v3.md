# S16 — glyphcnn-v3: target-class over-representation (t-20261012-66e3)

**Artifact:** `models/glyphcnn-v3.npz` (234 601 B) + `recipes/glyphcnn-v3.json`,
trained 2026-10-12 by `tools/train_v3_targets.py` (committed here — the exact
launcher that ran). v2 stays untouched in the repo.

**Val acc 0.9394** vs 0.8921 for the committed v1/v2 recipe (same architecture
`conv3x3(8)-pool-conv3x3(16)-pool-fc96-fc62`, same split, same seed protocol,
data sha `e67bef5dbaf05eaa`, 397 s on the 2-core box).

## The single variable

After the base v2 dataset (`--per-class 200 --epochs 34 --generator-sheets 400`)
is built, the target classes get 3x total representation (2 extra synthetic
crops per class, `T.render_crop`, seed+777 stream). Targets = the classes the
head tree still loses, measured, not guessed:

- `l 1 i I 0 O d` — pericles' ruled lever (S10b ruling point 6);
- `a u t R S b E T r j U L` — the observed confusables from the head-tree
  item-level table (a→u x5, t→R x4, l→I x4, I→l x3, r→I/j x2, U→I x2, S→b x2,
  i→1 x2, E→T x2, L→I x2).

Nothing else differs — no reader, gate, or recipe-file change. This PR ships
the weights + recipe + this report; the swap-in behind the existing glyphcnn
gate is barry's/pericles' call.

## Screens (in-process, plain route, both suites, seed 1 first)

Suite `b2c460d2fb5a` (seed 1), swap reproduced by placing v3's bytes at
`models/glyphcnn-v2.npz` in a scratch checkout of the wave-6 tree `ef6f180`
(the exact configuration proposed for the swap — no code change at all):

| state | easy | hard | median / p95 |
|---|---:|---:|---|
| wave-6 tree, v2 weights | 54 | 12 | 1.43 s / 2.6 s |
| wave-6 tree, v3 weights | **56** | **12** | 1.40 s / 2.6 s |

Item-level vs v2 (join by `id`, never by string):
- easy **solved easy-0029** `R0setTE`→`ROsetTE`, **solved easy-0092**
  `Sdgnal`→`Signal`; **lost 0** (11 cells changed text, 2 crossed exact).
- hard gained `obstruction-0003` `M0ss`→`MOss`; lost `snow-0006`
  `OTTEr`→`0TTEr` (the twin confusion, other direction; 34 cells changed, 1+1).

vs clean main `a7168d5` on the same suite: easy 28→56 (kept 27, repaired 29,
lost 1 = `easy-0078`, which is the wave-6 lean's inherited loss — v3 itself
loses nothing against its parent tree); hard 9→12 (kept 9, repaired 3, lost 0).

## Held-out seed 2 FIRST (the acceptance ladder's gate)

Suite `ec64cd63790d`, everything else identical (in-process, plain route):

| state | easy | hard |
|---|---:|---:|
| wave-6 tree, v2 weights | 46 | 14 |
| wave-6 tree, v3 weights | **52** | 14 |

- easy **52 vs 46 = +6, held-out, same sign as seed 1** — 7 solved, 1 lost:
  solved easy-0002 `IVOBY`→`IVORY`, easy-0017 `TUNDBA`→`TUNDRA`,
  easy-0036 `BEAC0N`→`BEACON`, easy-0038 `Vap0r`→`VapOr`,
  easy-0050 `VEBTEX`→`VERTEX`, easy-0089 `COBAL`→`CORAL`,
  easy-0091 `W1LL0W`→`WILLOW`; lost easy-0073 `VAPOR`→`VAP0R`.
- hard unchanged (14/14; 39 cells churned text, none crossed exact).
- Seed sum: **easy +8** (seed 1 +2, seed 2 +6), consistent direction.

## What is and is not claimed

- **Claimed:** v3 > v2 as a model (val +4.7 pts; held-out +6 easy / +2 seed-1,
  no hard loss vs main), at unchanged latency and with zero code delta.
- **Not claimed:** the 98/95 bar (a single lever, not the solution); the
  residual twin errors go both ways (easy-0073, snow-0006 are v3 costs);
  small-n caveat — 2 and 7 flips per seed, so treat +2/+6 as a stateful
  direction, not a precision estimate. The class itself (case/digit twins) is
  corroborated across three independent sources (this screen, barry's
  rulebook, Iris's classified 12 non-exact easy items).
- **Next (acceptance ladder rung 3):** three-run proof on this swap
  configuration (bench, seed 1, both suites, serialized under the bench lock)
  — running next; numbers land as a comment here + a follow-up commit on this
  branch.

*Provenance stamps: suites seed-1 `b2c460d2fb5a` / seed-2 `ec64cd63790d`; trees:
wave-6 `ef6f180`, clean main `a7168d5`; route: in-process `baseline.read_text`,
no family (same as the CLI on the plain path); rows kept at `/tmp/v3screen_rows.json`,
`/tmp/pr27w6_rows.json`, `/tmp/s2_v2_rows.json`, `/tmp/s2_v3_rows.json`.*
