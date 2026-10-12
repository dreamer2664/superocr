# S10b — does not replicate: the CNN piece policy, behind a default-off flag (12 Oct)

Task `t-20261012-1a14`. **Official-chain claim: NOT met.** This report leads
with the failure, as the ruling requires.

## The headline, honestly

The policy this task was asked to wire (a confidence-gated CNN fallback inside
the floor reader) was measured first and **the gate is a dead lever**: on the
canonical suite it is flat at 28/100 easy in every cell (best 29), 9/100 hard
in every cell. The floor's template confidence is saturated — it reports 1.0
on ~98% of its pieces, including the ones it gets wrong — so there is nothing
for a gate to gate.

What did move the canonical suite was a different policy: keep the floor's
layout (segmentation, splits, word grouping, case rule) and let glyphcnn-v2
read **every** piece. Canonical suite (seed 1, hash `b2c460d2fb5a`): easy
**28 → 38**, hard **9 → 11**. Then the held-out check at seed 2 (fresh suite,
hash `ec64cd63790d`, protocol unchanged) came back:

| | floor | policy | delta |
|---|---|---|---|
| easy, seed 1 (canonical) | 28/100 | 38/100 | +10 |
| **easy, seed 2 (held out)** | **36/100** | **36/100** | **0** |
| hard, seed 1 | 9/100 | 11/100 | +2 |
| **hard, seed 2** | **7/100** | **7/100** | **0** |
| easy, pooled 200 | 64 | 74 | +10 (repairs 18 / losses 8; sign test p = 0.076) |
| hard, pooled 200 | 16 | 18 | +2 (repairs 5 / losses 3; p = 0.73) |

**The exact-match gain does not replicate.** Repairs and losses cancel at
seed 2 (easy 5/5, hard 1/1); pooled, the easy effect is suggestive at best
(p≈0.08) and the hard effect is noise. What does hold at both seeds: the
per-character read of easy is better (89.1→92.5, 90.0→91.1). One wrong
character still loses the whole word — that is the physics of this bar, and
at this accuracy level single-glyph fixes are traded backwards and forwards
item for item.

**Status of the artifact:** the policy ships behind an explicit **default-off
flag** (`SUPEROCR_PIECE_CNN=1` enables it; `PIECE_MIN_PROB`, default 0.3).
With the flag off, `baseline.py` output is byte-identical to main — verified
against the clean `a7168d5` chain on live images. Research-grade only; no
official-chain language, no promoted gain.

## Tests run on the wired chain

* flag off == clean main `baseline.py` byte-for-byte (live comparison);
* flag on == `tools/s10b_probe.py --policy cnn` byte-for-byte (the wiring
  implements the measured policy, not an approximation);
* `tests/test_baseline.py` with the flag off: all floor bars hold (dark-on-dark
  char 0.533, snow char 0.963);
* mirror self-check in `tools/s10b_sweep.py` still matches the post-S7c chain.


## What was measured, and how

`tools/s10b_gate.py` is a faithful mirror of `baseline.py`'s chain whose
per-piece character decision is a policy (`floor`, `gate`, `cnn`). The mirror
self-checks against the real chain (`--check`): under `floor` it must reproduce
`baseline.read_text` byte-for-byte, and it does (sampled per image; the sweep
tool refuses to print a table if any image drifts — it caught a real
divergence on its first run, the missing SAME_SHAPE case rule).

`tools/s10b_sweep.py` makes ONE instrumented pass per suite, recording every
piece (template score, height, word cap) plus the CNN's opinion on the same
normalised 24×24 crop the trainer uses, then reconstructs the read for ANY
(gate, min-prob) pair. One pass ≈ 6 minutes; an official bench run ≈ 15.

## Detail 1 — the confidence gate buys nothing

In-process, exact reconstruction, official suite hash `b2c460d2fb5a`:

| | floor | best gated cell | CNN on every piece |
|---|---|---|---|
| easy | 28/100 | 29/100 (gate 0.9, p≥0.3) | **38/100** |
| hard | 9/100 | 9/100 (every cell) | **11/100** |

The gate is flat across gate 0.3–0.95 × min-prob 0.3–0.9 because the floor is
**saturated-confident**: at gate 0.9 only **46 pieces in 100 easy images**
score below it — the template matcher reports 1.0 on ~98% of its pieces,
including the ones it gets wrong. On hard the gate does fire (396 pieces,
297 flips at gate 0.9) and still moves nothing: the layout is broken, so
repairing single glyphs cannot produce an exact string.

Conclusion: "confidence-gated fallback" as literally specified is not
promotable. It is not a wiring bug; it is the floor's confidence signal.

## Detail 2 — the measured lever is layout × eyes

Keeping the floor's layout (its segmentation, touching-glyph splits, word
grouping) and letting the CNN read every piece reads **38/100 easy, 11/100
hard** in-process — above the floor (28/9) and above the CNN's own reader
(31/8). The two halves are complementary: the floor knows where the glyphs
are, the CNN knows what they are.

**Official confirmation, one run** (`tools/s10b_probe.py --policy cnn`,
suite hash `b2c460d2fb5a`, seed 1): **easy 38/100, hard 11/100** — exactly the
in-process prediction. Three-run proofs for both arms (floor ×3, cnn ×3) run
from a frozen clone at `bdfd428` so the commit under proof cannot move.

Policy variants that were measured and NOT promoted (in-process, same pass):
gate<0.9 → 29 easy; gate<1.0 (replace every imperfect floor piece) → 27, worse
than the floor's 28; CNN only where the floor is imperfect → 27; CNN-side
confidence floors (accept only p≥0.9) → 35. With the floor's case rule off:
floor 14, cnn policy 30 — the height-based case rule is worth more than the
CNN's own case calls, and it keeps acting on whichever character survived.

## Composition with S8 (#27, barry) — the lever does NOT compose; it goes negative

Measured after barry's waves 1-5 (head `879148fd`, easy 51 / hard 12 in-process): a scratch merge
of this branch with that head (conflict resolved mechanically — these 4 lines slot after his
rerank vote), in-process, quiet box, seed 1 canonical, all 200 items.

| tree | easy | hard |
|---|---|---|
| #27 head alone (this flag OFF — item-identical on all 200 items) | **51/100** | **12/100** |
| merged, `SUPEROCR_PIECE_CNN=1` | **47/100** | 12/100 |

Easy: 3 solved, **7 lost**, net −4. Every loss is the class this report already named —
letter↔digit and case twins, now traded backward against a stronger base
(`dune`→`Oune`, `sabl`→`sab1`, `18`→`J8`, `vellu`→`ve11u`). The honest consequence: the
"+10 on the floor" headline of this report is **superseded once the rescue+gate land** — on the
rescued chain the same policy is a net loss, and the template side dominates it on every class
it touches. The flag stays OFF; this section exists so the record says that before anyone reads
the floor comparison and reaches for the switch.

## What the policy repairs and what it costs

Item-by-item against the floor's official runs (same suite, seed, both
official bench reports):

| | kept | repaired | lost | net |
|---|---|---|---|---|
| easy | 25 | 13 | 3 | 28 → 38 |
| hard | 7 | 4 | 2 | 9 → 11 |

Per-character accuracy: easy 89.1% → **92.5%**, hard 33.2% → **50.7%**. Hard
exact barely moves (+2) because exactness at 22 characters demands ~99.8% per
character; the reading underneath nearly doubles.

All five losses are one class — **letter↔digit confusions the CNN makes where
the template was right**: `dune→0une`, `basil→basi1`, `zigzag→z1gzag` (×2),
plus `easy-0073`. That is a clean follow-up for the next training round (over-
represent l/1/i/0/O/d on pieces at native raster scale) or a tiebreak rule on
those pairs only.

**Tested and rejected — the letter↔digit tiebreak.** Because all five losses
sit on the letter/digit boundary, the obvious repair is "on a letter-vs-digit
disagreement, trust the floor". Measured on the recorded rows it changes 23
easy and 44 hard items — and both directions: `dune→0une` is repaired while
`saffron→saffr0n` and `cobalt→c0balt` are broken. Net **0 easy, +2 hard**:
not a policy, a coin flip with a story. Rejected. The real fix is training-
side: over-represent `l/1/i/0/O/d` on pieces at native raster scale so the
CNN stops confusing them, instead of papering over it with a rule.

Failure mix after the policy (tools/suite_char_analysis.py): easy 62 failures
= 17 within one edit, 31 within two, 7 case-only, 1 spacing-only. The case and
spacing residuals are the decision-layer headroom that sits ON TOP of 38/100.

## Held-out replication — the full record

The canonical suites are one sample. I built a second suite from the same
generator at seed 2 (hash `ec64cd63790d`) and re-ran the whole policy
comparison on it, unchanged. What survives and what does not:

| | floor | policy | delta |
|---|---|---|---|
| easy, seed 1 (canonical) | 28/100 | 38/100 | **+10** |
| easy, seed 2 (held out) | 36/100 | 36/100 | **0** |
| hard, seed 1 | 9/100 | 11/100 | +2 |
| hard, seed 2 | 7/100 | 7/100 | 0 |
| easy, pooled 200 | 64/200 | 74/200 | +10 (repairs 18 / losses 8, sign test p = 0.076) |
| hard, pooled 200 | 16/200 | 18/200 | +2 (repairs 5 / losses 3, p = 0.73) |

So the policy's canonical-suite gain does **not** replicate at seed 2: exact
score unchanged, repairs and losses in balance (easy 5/5, hard 1/1). Per
character it improves easy at BOTH seeds (89.1→92.5 and 90.0→91.1) and is
inconsistent on hard (+17.5 at seed 1, −1.0 at seed 2). Pooled over 400 items
the policy is still net positive, but the easy effect is suggestive at best
(p≈0.08) and the hard effect is noise. This is stated here, not buried,
because the number that ships (38/11 on the canonical suite) is a real
measurement and a thin claim at the same time.

**Killed by the same check — the image-cap case rule.** The seed-1 find that
the case rule breaks on words with no ascender (`crane → Crane`) looked like
+5 easy on the floor and +3 on the policy when the reference height is the
image cap at threshold 0.80. At seed 2 it *reverses* (floor 36 → 35, policy
unchanged). Not shipped. The mechanism (word-cap is fragile) stays a
hypothesis with one supporting and one contradicting sample, and belongs in a
report, not in the chain.

The honest read of both held-out results: single-glyph decisions are being
traded backwards and forwards at this accuracy level — an item is lost by one
wrong character and won back by another. The levers that move exact strings
are layout (segmentation, splits, grouping) and case/spacing decisions, not
the glyph classifier axis alone. That is what the failure mix said before the
held-out check, and the held-out check is what makes it credible.

## The wiring (landed, rebased on merged S7c)

Design: **flag off by default** — `read_text` is the pure floor, byte for
byte. With `SUPEROCR_PIECE_CNN=1`, the CNN reads a piece when its probability
≥ `SUPEROCR_PIECE_MIN_PROB` (default 0.3), otherwise the floor's template
answer stands; the floor keeps segmentation, splitting, word grouping and its
case rule throughout. Implemented as a **32-line change to `baseline.py`**
(flag + lazy loader + three lines in the piece loop) plus
`readers/piece_cnn.py` (the single place where a piece becomes the 24×24
ink-bright crop the trainer uses). Branched and rebased **on merged S7c**
(PR #25) — the family masks and this flag are orthogonal and need no stacking
order. Checks run on the final wiring:

* flag OFF == clean-main `baseline.py` byte-for-byte on live images;
* flag ON == `s10b_probe --policy cnn` byte-for-byte (the wiring implements
  the measured policy, not an approximation of it);
* `tests/test_baseline.py` with the flag off: all floor bars hold;
* reference pack (Carlo's 26 scored tiles, flag on): floor exact 0/26 char
  8.2% → wired exact 1/26 char 8.1% — flat-to-+1 on a 26-tile sample of the
  hardest material; not the bar, reported as measured.

## Detail 3 — the floor number everyone quotes is stale

Measured officially on merged main (`a3ab207`, suite hash `b2c460d2fb5a`,
seed 1): `baseline.py` reads **easy 28/100, hard 9/100**, one run.

The 22/6 in the S5 report came from the S5-era classic reader through
`bench_adapter`; that path today routes to `reader.py`, the pre-S1
family-aware chain, which reads **3/2**. So the current official picture is:

| reader | easy | hard |
|---|---|---|
| `reader.py` (pre-S1 family chain) | 3/100 | 2/100 |
| `baseline.py` (floor) | **28/100** | **9/100** |
| `cnn_reader.py` + committed weights | 29/100 | 6/100 |
| `cnn_reader.py` + glyphcnn-v2 | **31/100** | **8/100** |

The floor to beat is 28/9. S7c's family masks should be measured against that.

## Files

* `tools/s10b_gate.py` — the policy boundary (mirror + policies + CNN loader)
* `tools/s10b_sweep.py` — one-pass threshold reconstruction (self-checking)
* `tools/s10b_probe.py` — bench-compatible CLI for any policy
* raw reports: `/tmp/s10-bench-main18-baseline/`, `/tmp/s10b-bench-cnnpolicy/`
