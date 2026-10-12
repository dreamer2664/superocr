# superocr — the plan

**The bar (Carlo, 11 Oct 2026).** Read hard images exactly, case-sensitive, then
put the text where it belongs. Measured, not asserted:

| suite | what it is | required |
|---|---|---|
| easy | plain text, clean background | **≥ 98/100** |
| hard | distortion, snow / spiderweb / split / stitch / strippy / cut / collage / corrosion / cross-shadow / darts patterns, semi-transparent obstruction, dark-on-dark, many fonts, several words | **≥ 95/100** |

- **Three consecutive runs** must each clear the bar — stability is part of it.
- **Live demo:** image (a file, or a screen region) → typed into a text box,
  median ≤ 10 s end to end.
- **Reproducible from a clean clone:** seeds, commands and the run report are
  committed. Every number in the README links to a report file.

**The honesty rule (do not bend this).** Some hard families will resist: these
reference images are adversarial by design. A report that says "92/100 on
spiderweb, here is the failure gallery, here is what we tried" is a **good**
report. A report that rounds a number up, or quietly drops a family from the
count, is a failed task. We publish what is true.

## Status — 12 Oct, morning (what shipped, with receipts)

| group | state | evidence (on main unless noted) |
|---|---|---|
| S0 the judge + suites | **done** | `bench.py` + `BENCH.md` (17c5026); reference pack labelled tile by tile |
| S1 classic reader | **done** | floor landed (8a0056a): easy 40 / hard 9 (seed 7, n=10) — the floor to beat |
| S2 learned reader | **done** | CNN (01394ee, 89.2% glyph val) + confidence chain (d1a6) |
| S3 hard families | **done, honest numbers** | obstruction/dark-on-dark + split/stitch/strippy/cut; stages diagnosed (reports/stage-diagnosis.json) |
| S4 the product | **done** | typer (285eaa3); browser demo (0c85fb9): median 6.6–7.1 s vs the 10 s bar, where-measured labeled |
| S5 proof | **done** | three-run proof (0553923): classic 2/100·1/100 · CNN 29/100·6/100 — identical across runs |
| S6 stretch | **done** | held-out rework (266d405): +3.1 combine is real; augmentations +0.8; self-train +0.8; winner's curse documented |

**Where we are, plainly:** best merged reader ≈ 22/100 easy, 6/100 hard. The bar is 98/95. Proof machinery, demo and galleries all work; the reader is the whole game now.

## The front — morning shift, 12 Oct (carlo's order: all hands, 100% superocr)

Board task ids carry the score; this file carries the map. One job each, priority 1.
**And the chain continues — nobody stops while jobs are open:** finish your job → claim the
next superocr job the same hour → when superocr has nothing left, take the next job on the
chatcode board. Superocr is the priority, not the only thing; blocking is a one-line message
followed by picking something else up. Idle is a docking (day session: −500 at 25 minutes of
silence).
*Target: the product fully functional end to end, and the easy bar pushed as far as it honestly goes — every candidate number shipped with its three-run proof.*

**S7 — the hard walls** *(marcus-aurelius — t-20261012-e199, the most demanding job)*
The five 0% families, one at a time, with `reports/stage-diagnosis.json` as the map:
collage / cross-shadow / darts = segmentation walls; corrosion = classifier wall;
dark-on-dark = finish the vignette stroke loss (binarisation fixed, char 52.4).
Ship only measured gains, gallery honest. Plus the wide-M fix: repro is on main
(`tools/repro_wide_m.py`) — wide-M must come down to 1 piece, the genuine il-pair must stay 2.

**S8 — the easy war** *(barry — t-20261012-ac4f)*
easy is the closest bar and the official suite reads 22/100. Segmentation robustness on
touching/over-split glyphs, case-twin + rerank tuning, native-scale matcher, and the CNN
integrated into the easy path behind a confidence gate. Integrate only held-out survivors
(the combine +3.1 is real; most augmentations were not). Held-out seeds in every headline.

**S9 — the product path** *(cormac — t-20261012-5c63)*
Fully functional end to end: auto-mode latency under 10 s on every probe (strippy 26.0 s /
split 12.4 s today — the documented path is a cheap pre-classifier to skip chains, or faster
chains), clean-clone smoke of typer + demo + bench running straight from the README, and a
README a non-programmer can follow.

**S10 — training + truth** *(scott — t-20261012-4447)*
Raise the learned component (89.2% glyph val today) with a committed recipe + seeds +
measured val, wired in via the confidence-gated fallback — and keep the truth anchor:
three-run proofs for every claim, official suites, no in-sample headline numbers.

## Conventions

- **Where the code lives:** `dreamer2664/superocr` (the project's own repo:
  branches `agent/<name>/<task-id>`, pull requests, issues, demo page). The copy
  in `projects/superocr/` inside chatcode is an automatic read-only mirror for
  visibility - never edit it by hand, the next mirror run overwrites it.
  Task and vote coordination stays here, on the chatcode board and bus.
- The team's token covers both repositories. The red line (never touch
  `captchaproject` / `captchaprogram`) is unchanged and absolute.
- **Pre-flight before every PR:** `bash tools/preflight-pr.sh <branch>` — it lists
  every file that would vanish if the branch merged and how far behind main it was cut.
  Four stale-cut PRs were caught by hand on night one; the script is the rule now.
- Python 3.11, stdlib + numpy/Pillow only (CPU, no pretrained model downloads).
- Tests offline, fast, seeded; CI runs the suite on every push.
- Heavy artefacts (datasets) are **generated**, not committed.
- Coordination: tasks, votes and discussion live on the chatcode board/bus.
