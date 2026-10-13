# S25 — the hard segmentation wall: piece-count reconciliation (t-20261013-0956)

**Question.** S22 mapped the hard residue (21/100 exact on the shipping route)
as 83% segmentation-class at position level. Is a piece-count prior —
re-merge/re-split arbitration when the reader's word count disagrees with the
best lexicon parse — a lever on those misses, or is the "segmentation class"
a symptom of something upstream?

**Method.** Fresh collection on my box (seed-1 canonical suite, hash
b2c460d2fb5a): the shipping route (`python3 tools/reader_lex.py {image}`)
per hard image, plus an in-process replication of baseline's mask path
(autocontrast → otsu with the S8 lean → polarity guard → despeck → trim →
deskew → `R.segment`) to record the reader's word-piece structure per item.
`tools/s25_piece_gap.py --collect` / analysis mode. The collection reproduces
the 4th-box receipt exactly (21/100 hard).

## 1. The piece-count gap, classified by failure MODE

On the 79 hard misses: **fewer 27 / more 25 / equal 27** reader-words vs
label-tokens. But the classes decompose by failure mode, not by fixable
arbitration:

| mode | families (misses) | signature | repairable by count arbitration? |
|---|---|---|---|
| **mask collapse** | spiderweb 8, collage 8, cross-shadow 6, darts 4 | whole line → 1–2 junk words (`?I4`, `M?`); reader_words ≪ label_tokens | **no** — ink/background merges before segmentation |
| **stroke destruction** | corrosion 7, strippy 4, stitch 5, snow 2 | unreadable glyph fragments (`zvwvwr`, `zztlz`); reader_words > label_tokens | **no** — joining fragments cannot rebuild `reef` from `zvwvwr` |
| **glyph/case, structure intact** | split 5, cut 2, obstruction 3, dark-on-dark 3, snow 3, … | reader_words = label_tokens | no — these are the S24 lanes, closed by converging negatives |
| **pure count errors** | stitch 2, snow 1, split 1 | tokens correct (case aside), count wrong | **yes — the lever under test** |

The auto-family route does **not** crack the collapse families either
(`baseline --score --families spiderweb,collage,corrosion`, seed 1:
collage char 1.7%, corrosion 11.7%, spiderweb 11.8% — exact 0 everywhere).

**Per-family exact on the shipping route** (this collection):
strippy 0/8 · collage 0/8 · corrosion 0/8 · cross-shadow 0/8 · darts 0/8 ·
spiderweb 1/9 · stitch 1/9 · split 3/9 · dark-on-dark 3/8 · snow 4/9 ·
obstruction 4/8 · cut 5/8. **Six families at ~0 = 48 of the 79 misses.**
That is where the 95-bar lives, and it is image-side — consistent with S24's
converging negatives.

## 2. The count-prior lever, measured

Ceiling first: misses where joining ONE adjacent token pair or dropping ONE
token reproduces the label (case-folded) = **4/79**. Two of those carry case
errors in the same line (split-0001, stitch-0007) that S24 already closed —
count arbitration alone does not fix them. **Pure count errors: 2/79.**

Grammar facts that make a guarded rule zero-risk by construction (checked on
all 200 seed-1 labels):

- no label ever contains two adjacent digit-only tokens (the grammar inserts
  at most one number token, 1–3 digits: `%d %02d %03d %d%d`);
- no lexicon word is shorter than 4 chars, so a single alpha character is
  never a legal token.

### The rule (S25 candidate, measured in-process on the collected reads)

1. **digit-join**: join adjacent digit-only tokens when the join is ≤3 digits.
2. **alpha-orphan-drop**: drop a len-1 ALPHA non-lexicon orphan directly
   before a clean lexicon token (the mirror of R5's after-rule; digits are
   legal single tokens and are never dropped — an earlier unrefined version
   that dropped digit orphans measured net ZERO: fixed 2, broke 2).

### Result (hard, seed-1, this box)

| route | exact |
|---|---|
| reader_lex + R5 (collected) | 21 |
| + S25 rules | **23** (fixed stitch-0005 `L talon…`, snow-0008 `2 3`→`23`; broken 0) |

EASY LOSS CHECK (same rule, easy suite, collected reads): **easy 73 → 73,
0 fixed, 0 broken** — zero losses on both suites.

**Wired**: the rule ships as `_s25_count_repairs` in `tools/lex_projection.py`,
called at the END of `fix_line` — i.e. POST-projection, on tokens that have
already been through `_repair_tokens` (R5) and `fix_token` (case/lexicon
projection). The placement is load-bearing and the end-to-end bench caught
it: a first wiring that ran S25 inside `_repair_tokens` (pre-projection)
measured hard 22, not 23 — on stitch-0005 the raw output is
`L alon sha le 007`; the orphan `L` can only be dropped once `fix_token` has
projected `alon` → `talon` into a clean lexicon word, so the orphan-drop has
to see the POST-projection token stream. (This is also why the in-process
replay — which applied S25 to already-projected text — could not catch it.)
`tests/run_all.py` 22/22 green on the branch. End-to-end stamped bench (the
receipt below) is the ground-truth composition: **easy 73 / hard 23**.

## 3. Verdict

- The count-arbitration lane is **closed at +2**: the measured lever is
  net-positive on the residue (21→23 hard) but its entire ceiling is 2 items;
  the other 77 misses are mode-decomposed upstream (48 mask/stroke, 29
  glyph/case/other). Nothing further is available from the text layer.
- The hard wall is now precisely located: **six families at ~0 (48 misses)
  fail at or before the mask**. Any future lever on the 95-bar must be
  image-side (mask or native-raster recognition), not post-pass.

## Files

- `tools/s25_piece_gap.py` — collect/analyse tool (route-exact mask replication)
- `reports/s25-piece-gap/hard-reads.jsonl` — 100 hard items: want/got/exact/
  reader_words/glyph_pieces/label_tokens
- `reports/s25-piece-gap/easy-reads.jsonl` — same for easy (loss check)
- `reports/s25-piece-gap/receipt2/` — stamped end-to-end bench on the wired
  branch (easy 73 / hard 23); `receipt/` holds the first (pre-projection)
  wiring bench, kept as the composition-order evidence (hard 22)
