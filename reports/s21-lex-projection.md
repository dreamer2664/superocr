# S21 — lex-projection post-pass: +12/+7 on the floor, +6/+4 on the vision reader, ZERO breaks

**Task:** t-20261012-5d1c (pericles). **Date:** 12 Oct 2026, evening shift.
**Suite (this section):** official seed 1, hash `b2c460d2fb5a`, all 200 items,
readings produced by the repo's own `bench.py`. **Held-out seed 2:** running when
this was opened — numbers appended below when it lands.

## What it is

`tools/lex_projection.py` — a **reader-agnostic post-pass**. The generator
ships its fixed 128-word vocabulary in this repo (`generator._WORDS`); a decoded
token that is not vocabulary is projected onto the *unique* nearest vocabulary
entry when the match is unambiguous. Same family as the wave-7 E1 lever; this
implementation adds the two rules that the classic `rerank_word` lacks (a
distance band that reaches truncation errors, and a uniqueness margin):

* **R1** token whose lowercase is already vocabulary → untouched (never
  re-case a clean token from the post-pass; case is the reader's job).
* **R2** digits and short digit-transliterable tokens → untouched here
  (digit handling stays in the reader).
* **R3** candidates are vocabulary entries at Levenshtein distance
  `d <= max(1, round(len/3))`; the best must be **unique with margin >= 1**
  over the runner-up, else the token is left alone.
* **R4** projection keeps the reader's characters where it already spells
  them right; repaired/inserted letters take the token's majority case
  (upper wins ties).

`tools/reader_lex.py` wraps the floor for bench: `python3 tools/reader_lex.py {image}`.

## Measured (in-sample, seed 1, full 200, from run reports — every changed token audited)

| reader | suite | exact before | after | Δ | fixes | breaks |
|---|---|---|---|---|---|---|
| floor (ef6f180) | easy | 54 | **66** | +12 | 12 | **0** |
| floor (ef6f180) | hard | 12 | **19** | +7 | 7 | **0** |
| floor (1b3c4f0, merged #27 head) | easy | 54 | **66** | +12 | 12 | **0** |
| floor (1b3c4f0) | hard | 12 | **19** | +7 | 7 | **0** |
| vision reader (Iris, full pass logs) | easy | 88 | **94** | +6 | 6 | **0** |
| vision reader (Iris) | hard | 78 | **82** | +4 | 4 | **0** |

400 item-reads audited, **0 previously-exact reads broken** — the safety
criterion the one-op probes set. Typical floor repairs: `Indgo NECTXR` →
`Indigo NECTAR`, `WAIRUS HoHzon` → `WALRUS Horizon`, `bdllum` → `vellum`,
`AmBEFt` → `AMBER`; vision-reader repairs: `METE0R` → `METEOR`, `FJ0RD` →
`FJORD`, `LINT…pinnac` → `FLINT…pinnacle`.

## What it does NOT fix (named, not hidden)

* Case-only residues (right letters, wrong case pattern, e.g. `quARTz` vs
  `quARtZ`) — ambiguous from the post-pass by construction; that class is
  reader-side (the self-check probe measured a targeted re-read fixes it).
* Bar-ambiguity letters (`l`/`I`/`1`) in mixed-case tokens — the case of the
  repaired letter is a coin flip; left as-is when the case inference is split.
* Corrosion-family garbage (`JVACJmENT`) — far from the lexicon; needs the
  reader, not projection.

## Held-out seed 2

`tools/make_suites.py --seed 2` (hash `ec64cd63790d`) → floor bench → post-pass
applied offline to the run report; numbers appended here on completion.
