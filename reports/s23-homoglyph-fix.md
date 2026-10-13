# S23 — digit-homoglyph second-class fixer: measured on the shipping route

**Task:** `t-20261012-5985` (the invite at `t-20261012-5d1c`).
**Measured against:** `tools/lex_projection.fix_line` at current main `7a92ce1` (R1–R5 plus the merged S25 count post-pass; `lex_projection.py` is unchanged from `c067795`).
**Decision:** **do not wire a new production pass.** The conservative R4-case policy adds no exact matches after the shipping lex projection on either model arm. The uppercase policy can turn two already-correct shipping outputs into case errors on v3.

This is an offline, deterministic transformation ablation of four saved 200-row captures; no OCR reader was rerun. The plain-route positive deltas below are diagnostic only—the task is whether a second fixer adds value to the existing lex shipping path.

## Rule measured

For a token containing both letters and `0`/`1`, try `0 → o` and `1 → i` or `l`. Rewrite only when exactly one word in `generator._WORDS` matches, case-insensitively. Leave pure numbers, pure-letter tokens, tokens with other digits, non-vocabulary candidates, and ambiguous matches unchanged. The `r4` policy cases only repaired positions by the majority case of the token's existing letters (uppercase wins ties), matching `lex_projection` R4. `upper` is an intentionally aggressive control.

The 400 seed-1/seed-2 ground-truth labels contain **zero mixed letter-plus-0/1 tokens**. That protects an already-correct raw string from a direct substitution. It does **not** protect a pre-lex composition: an erroneous raw `v1olet` can become a valid but wrongly cased `vIolet`, after which R1 preserves it. The measured `upper` breaks below demonstrate that distinction.

## Results

Counts are exact string matches, `easy / hard`. Each seed has 100 easy + 100 hard items.

### Candidate alone on saved raw rows (plain route)

| Arm | Seed 1 before → after | Seed 2 before → after | Pooled |
|---|---:|---:|---:|
| v2, R4 case | 54/12 → 56/12 | 46/14 → 49/14 | **100/26 → 105/26** (+5 easy, 0 hard) |
| v3, R4 case | 56/12 → 57/13 | 52/14 → 54/14 | **108/26 → 111/27** (+3 easy, +1 hard) |

This does improve some raw-floor OCR strings, including `R0setTE → ROsetTE`, `v1olet → violet`, and `0TTEr → OTTEr`. It is not an incremental win after the existing shipping post-pass.

### Candidate before the current shipping lex route

The baseline column is current `lex_projection.fix_line(raw)`. The candidate column is `lex_projection.fix_line(homoglyph_fix(raw))`.

| Arm | Seed 1 before → after | Seed 2 before → after | Pooled |
|---|---:|---:|---:|
| v2, R4 case | 73/23 → 73/23 | 74/29 → 74/29 | **147/52 → 147/52** |
| v3, R4 case | 73/24 → 73/24 | 75/28 → 75/28 | **148/52 → 148/52** |

With R4 casing, **zero exact matches are added or lost** across 800 row-route evaluations. Output text is identical on 799/800 rows; the sole text-only change is v3 seed-2 hard `obstruction-0000`, where `Saffron h0L10w Gld?` becomes `Saffron hoLlow Gld?`. It remains wrong against `Saffron hOLlOw GLACIER 92`. So even the conservative policy is not literally a byte-for-byte no-op, but it yields no exact-score gain and makes one wrong string different.

### Uppercase control before the shipping lex route

| Arm | Seed 1 before → after | Seed 2 before → after | Pooled |
|---|---:|---:|---:|
| v2, uppercase | 73/23 → 72/24 | 74/29 → 75/29 | **147/52 → 147/53** (0 easy, +1 hard) |
| v3, uppercase | 73/24 → 72/24 | 75/28 → 75/28 | **148/52 → 147/52** (−1 easy, 0 hard) |

On v2 it makes 3 exact repairs and 2 exact breaks. On v3 it makes 1 repair and 2 breaks, plus one wrong-to-wrong text change. The two exact breaks are:

- `easy-0030`: correct `violet` becomes `vIolet` after the pre-pass;
- `easy-0075`: correct `ivory` becomes `Ivory` after the pre-pass.

The apparent v2 gains are not a safe reason to ship an uppercase rule: it is net-negative on the v3 arm and the case bit is not recoverable from the digit alone.

## Reproduction and four stamps

The input JSONs and full per-row output/diff JSON are committed alongside this report:

- `reports/s23-homoglyph-inputs/main-v2-s1.json` — SHA-256 `5fcc0e669d4bc5da4d8de3a4f0bd712472f14d2c55ced43d3a8ef83c8c83fd40`
- `reports/s23-homoglyph-inputs/main-v2-s2.json` — SHA-256 `3dc0f3519709c29d1c5ea07b624880561e79e60e90ef7ae0247c31f24ff0a965`
- `reports/s23-homoglyph-inputs/main-v3-s1.json` — SHA-256 `ef952c9e7c6ae5a1f8288bf37ac4c90c5812467a106487d3e17c61717ba0807b`
- `reports/s23-homoglyph-inputs/main-v3-s2.json` — SHA-256 `8929e34bdcfb37f7d73dbf4c1d74c79a78d55377f1ff09acec85f59f82c0a2b0`
- Full machine-readable screen: `reports/s23-homoglyph-screen.json`.

| Stamp | Value |
|---|---|
| `dir_hash` | Seed 1: `b2c460d2fb5a8f83c8d4c4b3893ff6eb05248f2444cbb1ff8acbe9531323fdd3`; seed 2: `ec64cd63790d8824b4f72c71d18dd953326c24da01d65d171938ae79beb549e8` (canonical suite directories). |
| `reader_command` | Saved raw captures were emitted by `python3 check_rows.py <reader-tree> <suite-root> <out.json>`; that script calls `baseline.read_text(img)`. This screen does not re-run the reader. The post-pass command is `python3 tools/s23_homoglyph_screen.py --policies r4 upper --json reports/s23-homoglyph-inputs/main-v2-s1.json reports/s23-homoglyph-inputs/main-v2-s2.json reports/s23-homoglyph-inputs/main-v3-s1.json reports/s23-homoglyph-inputs/main-v3-s2.json`. |
| `env` | Offline screen: Python 3.13.16 (GCC 14.2.0), Linux 6.1.158+ x86_64, glibc 2.41. Deterministic stdlib transform; no image/model inference or network access. |
| `scorer` | Exact case-sensitive string equality: `candidate_output == row["label"]`, reported separately for `easy` and `hard`. Lex baseline and candidate both use current `tools/lex_projection.fix_line` at `7a92ce1` (`tools/lex_projection.py` SHA-256 `64b9475dc6586b81f8adeba604e10bbe00ae46e2985abc07aa01892f717cba22`; unchanged from `c067795`). |

The reader-tree paths and their environment fingerprint are not serialized in the original row JSONs; their file hashes above bind the exact stored inputs. This report is an offline stored-row screen, **not** a replacement three-run reader receipt or a claim that the overall OCR acceptance bars are met.

Re-run the targeted tests and screen:

```bash
pytest -q tests/test_homoglyph_fix.py
python3 tools/s23_homoglyph_screen.py --policies r4 upper --json \
  reports/s23-homoglyph-inputs/main-v2-s1.json \
  reports/s23-homoglyph-inputs/main-v2-s2.json \
  reports/s23-homoglyph-inputs/main-v3-s1.json \
  reports/s23-homoglyph-inputs/main-v3-s2.json
```

Verification: `pytest -q tests/test_homoglyph_fix.py` → `7 passed, 5 subtests passed`; `python3 tests/run_all.py` → **23/23 files passed (340.21s)**, including the new tests; `py_compile` passes for the fixer, screen, and tests. No reader was modified and no fixer is wired into a shipping path.
