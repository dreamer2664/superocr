# S22 — the post-R5 residue map (t-20261012-dc2e)

**What this is.** After the ladder (#27, floor 54/12), the lex projection (#47, R1-R4)
and R5 (#49) landed, the shipping reader is `tools/reader_lex.py` = floor + lex. This is
the classified map of **everything still wrong** on the official suites, so the next wave
can target by class instead of by anecdote. Receipt-based and reproducible: no new claims,
the numbers below are the merged code applied to raw floor rows.

**Route measured.** `floor rows -> tools/lex_projection.fix_line` — exactly what
`reader_lex.py` runs (wrapper = floor output + fix_line). Raw floor rows:
`main-v2-s1.json` / `main-v2-s2.json` (my runs; seed-1 set verified **200/200
item-identical** to the committed floor receipt `reports/post27-screens/20261012T170353Z`;
seed-2 set under the pre-R5 lex reproduces the committed wrapper receipt `69/24` exactly —
and the +5/+5 below is R5's own gain there, not this task's). Lex file:
`tools/lex_projection.py` @ `b2f3004` (sha `79eb223e88e9`, R5 present).

## Totals after R5 (both official suites)

| suite | seed | exact | case-only | fewer-chars | more-chars | subs(n) | misses |
|---|---:|---:|---:|---:|---:|---:|---:|
| easy | 1 | **73** | 12 | 6 | 6 | 3 | 27 |
| easy | 2 | **74** | 14 | 5 | 4 | 3 | 26 |
| hard | 1 | **21** | 8 | 35 | 32 | 4 | 79 |
| hard | 2 | **29** | 8 | 35 | 22 | 6 | 71 |

*(`fewer`/`more` = fewer/more characters than the label — the segmentation signature:
fused pieces, dropped pieces, split pieces. `subs(n)` = same length, n differing
positions.)*

Pooled over the 200 reads per suite:

- **easy 147/200** (73.5 avg). The 53 misses are **~half case-only (26), 40% segmentation
  (21), 11% substitutions (6)**.
- **hard 50/200** (25 avg). The 150 misses are **83% segmentation (124), 11% case (16),
  7% subs (10)** — hard is a segmentation wall, full stop.

## What this says — three lanes, in order of size

1. **Segmentation owns hard** (124/150 hard misses, 21/53 easy misses). This is where
   the walls live (collage/corrosion/strippy/stripper-family reads produce whole-string
   garbage; the `strippy` misses below are representative). R5's joins shaved the easy
   side of it; the residue is full-piece fusion/splitting, i.e. the S8-lever-C/`split_wide`
   family plus the wall families. Corrosion remains 0/8 under every route measured today.
2. **Case-only is the biggest easy class (26) — and it is lex-immune BY DESIGN.** R1
   never re-cases a clean token ("case patterns are the reader's job"). Every one of the
   12-14 case misses is a reader-side case decision (`pINNaCLe`, `WREn`, `WALRUS taRn`...).
   Note for the record: lex-side re-casing and the image-cap case-rule were **already
   rejected** as levers earlier today — this class must be won in the reader's case logic
   (the wave-2..5 family), not in the post-pass.
3. **Substitutions are nearly gone** (6 easy, 10 hard): the matcher's top-8 already
   contains the right glyph for most of these; the residue is case/twin-adjacent or
   hard-family damage. Not a separate lane.

For reference, the bar gaps this map implies (pooled small-n caveats aside):
easy 73.5 -> 98 = **~25 items to find**; hard 25 -> 95 = **~70 items**. The map says where
they can plausibly come from: ~half of easy's gap is case-lane work; the other ~half plus
almost all of hard's gap is segmentation, with corrosion (16 reads, 0 correct) sitting
inside the hard number as its own unresolved wall.

## Reproduce (two commands)

```
python3 tools/s22_residue.py --lex main-v2-s1.json     # prints tables + full miss lists
python3 tools/s22_residue.py reports/post27-screens/20261012T170353Z-easy-hard.json  # pre-lex cross-check
```

Raw floor rows for both seeds are the `got/label` pairs of the committed receipts
(`reports/post27-screens/20261012T170353Z` for seed 1; the seed-2 wrapper receipt on main
for the seed-2 labels) — the script takes either shape, with `--lex` to apply the merged
post-pass.

*Provenance: my rows (in-process `baseline.read_text`, seed 1/2, suites `b2c460d2fb5a` /
`ec64cd63790d`); lex at `79eb223e88e9`; seed-1 floor rows item-verified against the
committed receipt; seed-2 control verified against the committed wrapper totals. Full
miss lists print from the script; easy lists are also in the PR description.*
