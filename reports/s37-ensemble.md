# S37 — offline ensemble probe: word-majority voting measured neutral-to-harmful, NO-GO

**Owner:** marcus-aurelius · **Task:** `t-20261013-1cbf` · **Date:** 13 October 2026 (evening)
**Question (pericles' assignment list):** can word-level majority voting across
the currently-invokable classic-stack members beat the best single arm
(shipping 73/23 seed-1) on the canonical suites, offline?

## Verdict

**NO-GO.** Every ensemble arm ties or loses to the OFF gate on canonical
seed-1. Nothing to ship, nothing to tune — the members do not disagree in a
way that carries information.

## Arms (fixed up-front, S51 gated template, before any numbers)

Members, all in-process on current main code (`tools/s37_ensemble_probe.py`):

| member | invocation | easy | hard |
|---|---|---:|---:|
| `off` | `fix_line(baseline.read_text(img, None))` — shipping wrapper | **73** | **23** |
| `nlex` | `baseline.read_text(img, None)` raw (floor, no lexicon) | 54 | 12 |
| `auto` | `fix_line(typer.recognise(img, "auto"))` — preclassifier single-chain + lex | 14 | 10 |
| `v7b` | shipping with `baseline._CNN = glyphcnn-v7b` (S31 Lever-2 slot swap) | 70 | 24 |

Ensembles — word-level exact-string majority, ties (incl. 2-2) resolve to the
`off` word, word-count mismatch falls back to the `off` read (rows flag both):

| arm | members | easy | hard | vs OFF |
|---|---|---:|---:|---|
| OFF gate | `off` alone | **73** | **23** | settled line reproduced exactly → probe VALID |
| E3a | off + nlex + auto | 73 | 23 | neutral |
| E3b | off + auto + v7b | 71 | 23 | **−2 easy** |
| E4 | off + nlex + auto + v7b | 73 | 23 | neutral |

All 800 member reads + 600 ensemble reads committed per item at
[`s37-ensemble-rows.jsonl`](s37-ensemble-rows.jsonl) (footer: rows=200,
wall 1015.4 s on a 2 GB box). Fallback counts (disclosed): E3a 56 count / 29
tie; E3b 47 / 18; E4 56 / 43 — on count-mismatched items every arm simply
returns the OFF read, so the ensembles can only differ from OFF where all
members agree on word count.

## Harness controls (three independent cross-checks, all exact)

- `off` reads: **200/200 byte-identical** to the S31 slot-probe OFF arm
  (barry, `reports/s31-slot-rows.jsonl`) and **200/200** to my independent
  S39 run-1 reads — fourth harness agreeing item-for-item on the shipping
  route.
- `v7b` reads: **200/200 byte-identical** to the S31 slot-probe `v7b-slot`
  arm, including its flip set (+obstruction-0003, −easy-0004/0082/0092) —
  the slot-swap injection reproduces across harnesses.
- `nlex` 54/12 matches the historical plain-floor ladder entry (54/12) —
  the floor core has been stable across the R5/lex merges for this measure.

## Why voting cannot help here (mechanism)

1. **The members are not diverse.** `nlex` is `off` minus its post-pass —
   they agree everywhere except where lex fires (help 17 / hurt 0 per the
   S43 census), so lex-corrected words are exactly the words `nlex` gets
   wrong: majority keeps the OFF word by construction. `v7b` diverges from
   OFF on a handful of items and loses more than it wins at read level
   (S31 L2: −3 easy / +1 hard). `auto` (current single-chain preclassify
   route) is far too weak to arbitrate anything: **14/10 measured here** —
   the historical AUTO ladder numbers (52/16) were the *old* all-chains
   confidence-arbitration auto, which the typer docstring itself records as
   gameable and replaced.
2. **The shared-miss pool is invisible to voting.** The residue is 82%
   segmentation (S43 census: 63/77) — on those items every member reads the
   same garbage or falls back on count mismatch. The matching-lane pool
   (9 case + 5 glyph) is also shared: all four members make the same case
   errors (they run the same floor matcher), so there is no dissenting
   correct read to majority-in. Voting combines *independent* errors; ours
   are the same error four times.
3. Where members do disagree (E3b), the disagreement is `auto`'s weakness
   or `v7b`'s recalibration loss dragging words away from OFF — measured:
   −2 easy, 0 hard gain.

## What this closes / what stays open

- **Closes:** offline read-level voting ensembles over the existing members
  (lexicon + preclassifier + slot-swap CNN voting, the S37 question as
  posed). Joins the measured-no list next to S51 (CLAHE), S31 (patch-class
  v7b integration), S30 read-level (net alone).
- **Does not close:** ensembles over *diverse* readers — the S54 word-level
  redesign (t-20261013-768c) would create a genuinely independent member
  (whole-word crops, jointly-normalised, new segmentation); voting OFF vs
  S54-reader vs lex variants is worth re-measuring **only after** S54
  produces a reader with its own failure profile. A fresh held-out protocol
  would be required (winner's-curse law).
- The `auto` 14/10 measurement is a useful incidental receipt: the current
  single-chain AUTO route should not be cited as a strong member anywhere.

## Bars

easy 98 / hard 95 / ×3 runs / demo ≤10 s / clean-clone: **NOT met** —
unchanged (shipping stays 73/23 seed-1, 74/29 seed-2; both hard numbers
named per discipline). This probe changed no read and ships nothing; its
value is the closed direction + committed rows + three cross-harness
identity checks.

## Repro

```
python3 tools/s37_ensemble_probe.py --suites <seed1-dir> --out reports/s37-ensemble-rows.jsonl
```

≈17 min on a 2 GB box (the `auto` member dominates: single-chain reads with
bounded fallback). Deterministic: repeated runs are item-identical (same
property class as s22-3x-settled; the OFF/v7b cross-checks above are the
evidence).
