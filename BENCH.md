# BENCH.md — how to be measured (t-20261011-2f3d, S0)

`bench.py` is the judge. It decides whether a reader is good enough, and it is
designed so that no one — including its author — can round a number up. This
page is the whole contract. Read it before writing a generator or a reader.

## The bar (JOBS.md, do not bend)

| suite | required |
|---|---|
| easy  | correct/total ≥ **98%** |
| hard  | correct/total ≥ **95%** |

The comparison is integer arithmetic (`correct*100 >= bar*total`), case-sensitive
and exact. Three consecutive runs (`--runs 3`) must each clear the bar for the
stability claim. A report that shows 92% is a good report; a report that hides a
family is a failed task.

## Suite format — what a generator produces

```
data/<suite>/manifest.jsonl     one JSON object per line
data/<suite>/images/...         image files, paths relative to the suite dir
```

One manifest line:

```json
{"id": "hard-0042", "image": "images/hard-0042.png", "label": "aB3xk",
 "family": "spiderweb", "tags": ["seeded", "font-a"]}
```

- `id` — unique in the suite, `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. Optional: if
  omitted it is derived from the image file's stem (which must then be a valid
  id — `snow.jpg` → `snow`). Duplicates are always an error.
- `image` — relative to the suite directory; must exist and be non-empty.
  `file` is accepted as an alias (some generators name it that); `image` is
  canonical. Extra keys (e.g. `seed`) are ignored.
- `label` — the exact answer, case-sensitive. `"?"` (or `"exclude": true`)
  means **not scored** (the reference pack uses this for tiles nobody can read
  with certainty). Excluded items are never sent to the reader, always reported
  by id — never silently dropped, never counted as correct, and never given a
  "got" that someone could later point at as a score.
- `family` — required; every report breaks the score down per family so a
  failure is attributable. Easy items can all be `"plain"`.
- `tags` — optional list of strings.

Blank lines and `#` comment lines are allowed in the manifest.

Generators must be **seeded and reproducible**, and the suite they produce must
be regenerable from a clean clone (`data/` is generated, never committed).

## Reader protocol — what a reader is

Any program that reads one image and prints the text to stdout:

```bash
python3 bench.py --reader "python3 readers/classic.py --image {image}"
```

- `{image}` is replaced with the image path; `{id}` is also available. If
  neither appears, the image path is appended as the last argument.
- stdout is the recognised text. The **only** leniency is one trailing newline;
  everything else is compared exactly (trailing spaces count as a miss).
- A non-zero exit is recorded as a failed item with the error — not a bench
  crash. Same for a timeout (`--timeout`, default 30 s).
- The command is `shlex`-split, not run through a shell. If you need shell
  features, pass `sh -c '...'` explicitly.

## What every run leaves behind

- `reports/<run>.json` — canonical: reader command, seed, run index, git
  commit, bars, per-suite and per-family correct/total/percent, every item's
  expected vs got, timings, excluded ids, and whether each bar was cleared.
- `reports/<run>.md` — the same numbers as tables, plus the failure list.
- `reports/gallery/<run>/<suite>/` — copies of **every** failing image (and a
  `gallery.md` giving id, family, expected, got). The ugly ones included.
- With `--runs N` (N>1): `reports/<ts>-stability.json` recording all N verdicts
  and the `passed_runs` count.

A number in the README must link to one of these files.

## Exit codes

| code | meaning |
|---|---|
| 0 | every suite cleared its bar in every run |
| 1 | it did not (the report says exactly where) |
| 2 | the bench could not run: bad/missing suite, bad manifest, bad arguments |

## Extras

- `python3 bench.py --validate` — parse and check the manifests only (fast CI
  check for generators: counts, families, missing images, duplicate ids).
- `--bar suite=NN` — override a bar; the report marks the run
  `bar_overridden: true`, so an overridden run can never masquerade as proof.
- `--no-gallery` — skip copying images (for a quick local loop; not for proof).
- `--seed` — recorded in the report; keep it fixed for any run you quote.

## Co-op mode (t-20261012-5e8a): one bench per box, legible long runs

Two rules, both learned the hard way on 12 Oct (parallel benches on one box
produced timeout artifacts indistinguishable from failures; two boxes quoted
the same suite at different numbers):

1. **The box lock.** Every scoring run takes a lockfile (`/tmp/superocr-bench.lock`
   by default, `SUPEROCR_BENCH_LOCK=...` to move it). A second bench finds it and
   **exits 3 naming the holder** — no reader process is started. A lock whose pid
   is dead is reclaimed automatically, so a crashed bench never wedges the box.
   `SUPEROCR_BENCH_NO_LOCK=1` bypasses both the taking and the refusing: use it
   only when you genuinely are alone, and say so when you quote the numbers.
2. **Item partials.** Every run streams `<run_id>-partials.jsonl` next to the
   report: one line per item (`suite`, `id`, `match`, `error`, `seconds`, running
   `correct`/`total`) and a final `{"event": "done", "counts": {...}}`. Long runs
   are no longer opaque: a watcher can see progress without waiting for the end.

### The four stamps (reproducibility gate, t-20261012-eb76)

Every report — JSON and markdown header — now carries the four stamps a reviewer
needs to decide whether two numbers are even comparable:

| stamp | where | what it answers |
|---|---|---|
| `dir_hash` | `stamps.dir_hash`, 64-hex sha256 | the same pixels? (byte-for-byte `tools/make_suites.py::dir_hash` — the gate re-hashes with that one) |
| `reader_command` | `stamps.reader_command` | the same reader? |
| `env` | `stamps.env` (python, pillow, numpy, cv2; `"absent"` when missing) | the same box, version-wise? |
| `scorer` | `stamps.scorer` (`--scorer author\|iris\|both`) | who produced the numbers? |

The names and formats are `tools/validate_report.py`'s contract (cormac's gate):
that validator is the consumer, so this file conforms to it, not the other way
round. Reports carry the suite path as `data_root` (as passed on the command
line, not resolved) — the absolute path is deliberately gone, because the gate
replaces path identity with content identity (the S14 lesson).

A review can reject a stamp mismatch without re-running anything. If two reports
disagree, diff the stamps first: same hash + same reader + same env + different
numbers is a real finding; anything else is a setup difference.

```bash
python3 bench.py --suite-dir data --suites easy --reader "python3 baseline.py {image}" \
    --scorer iris --report-dir reports
# refused loudly if another bench is running on this box (exit 3)
```

## Honesty checklist for whoever writes the final report

1. Quote the numbers from the JSON, not from memory.
2. If a family is under the bar, say so and point at its gallery.
3. Never present a `--bar` overridden run, or a `--no-gallery` run, as proof.
4. Three runs, all clearing the bar, or it is not stable yet.

## Reproducibility stamps (t-20261012-eb76, room decision t-ef72)

A bench number is only evidence if the reader can reconstruct the conditions
that produced it. On 2026-10-12 a reviewed headline read 0.707 on the author's
box and 0.302 on three other boxes over **hash-identical images**
(t-20261012-1d17) — nothing in the pipeline caught it, and the delta was only
found because two reviewers happened to run the reproduce commands. The gate
makes that class of failure structurally impossible to merge.

Every report a stamped bench writes carries:

```json
"stamps": {
  "dir_hash":       "<64-hex sha256 of the suite data root — tools/make_suites.py dir_hash>",
  "reader_command": "<the exact command string that was run>",
  "env":            {"python": "...", "pillow": "...", "numpy": "...", "cv2": "..."},
  "scorer":         "author" | "iris" | "both"
}
```

- **dir_hash** — content identity for the input bytes, replacing
  path identity (an absolute `suite_dir` proves nothing across boxes).
  Re-hashing is the only proof: a *quoted* hash is not a *re-computed* hash.
- **reader_command** — the full command, braces and all; must equal the
  `reader.command` the bench already records.
- **env** — the fingerprint of the box that scored the run. Optional
  libraries use the exact string `"absent"` (a legal value, not an error —
  cv2-optional chains are a supported configuration).
- **scorer** — who produced the number: the author, Iris (independent
  scorer), or both (two-scorer protocol).

### The reviewer side — no re-run needed

```bash
python3 tools/validate_report.py reports/<run>.json            # presence + format
python3 tools/validate_report.py reports/<run>.json --data data  # + re-hash the bytes
python3 tools/validate_report.py reports/<run>.json --data data --expect-scorer author
```

Verdicts: `PASS` (0), `FAIL` (1 — reject at review, reasons printed),
`UNSTAMPED` (2 — a pre-gate legacy report; regenerate it on a stamped bench
instead of hand-verifying). `--json` gives the machine-readable form,
`--compare-env` prints this box's fingerprint next to the stamp (mismatch is
*information* — the stamp describes the author's box — unless `--strict-env`).

### The four stamps at a glance

| stamp | where | what it answers |
|---|---|---|
| `dir_hash` | `stamps.dir_hash`, 64-hex sha256 | the same pixels? (byte-for-byte `tools/make_suites.py::dir_hash` — the validator re-hashes with that one) |
| `reader_command` | `stamps.reader_command` | the same reader? |
| `env` | `stamps.env` (python, pillow, numpy, cv2; `"absent"` when missing) | the same box, version-wise? |
| `scorer` | `stamps.scorer` (`--scorer author\|iris\|both`) | who produced the numbers? |

The bench side (t-20261012-5e8a, co-op mode) writes the stamps into every
report — JSON and markdown header — and takes `--scorer` on the command line.
Reports carry the suite path as `data_root` (as passed, not resolved): the
absolute path is deliberately gone, because the gate replaces path identity
with content identity (the S14 lesson).

A review can reject a stamp mismatch without re-running anything. If two
reports disagree, diff the stamps first: same hash + same reader + same env +
different numbers is a real finding; anything else is a setup difference.

Reviews bind to a sha (standing rule): an approving review names the head it
covered, and the stamps travel with the report, so a number and its
conditions can never drift apart silently again.
