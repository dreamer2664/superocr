# ONBOARDING — from clean clone to first receipt

_Everything below is offline and CPU-only. Repo constraint: Python 3.11,
stdlib + numpy + Pillow, no pretrained downloads, tests seeded and
network-free. If a step needs the network, it's a bug — report it._

## 1. Get the code

```
git clone https://github.com/dreamer2664/superocr.git
cd superocr
python3 -m pip install -r requirements.txt   # numpy~=2.0, Pillow~=12.0
```

## 2. Regenerate the canonical suites (≈7 min)

Suites are **generated, not committed** (heavy artefacts stay out of git).

```
python3 tools/make_suites.py            # writes data/easy + data/hard (100 items each)
python3 tools/make_suites.py --check    # determinism check
```

Verify you got the canonical suites before quoting any number: the seed-1
dir-hash prefix is `b2c460d2fb5a` (the independent seed-2 screen is
`ec64cd63790d8824`). Bench receipts embed the dir hash; `validate_report.py`
re-checks it.

## 3. Read one image

```
python3 tools/reader_lex.py data/easy/images/easy-0011.png
```

That is the shipping route: `baseline.read_text(img, None)` →
`tools.lex_projection.fix_line`. Expect the first lex call to be slow
(≈5–8 s cold, template-cache build) and ≈1 s warm — the demo bar counts the
warm median.

## 4. Run the bench (the judge)

```
python3 bench.py --suites data --runs 3
```

Writes `reports/<UTC-ts>-easy-hard.{json,md}` + a gallery. Contract lives in
[BENCH.md](../BENCH.md): the bar is easy ≥98/100, hard ≥95/100, **three
consecutive runs**, demo median ≤10 s, reproducible from clean clone. Current
shipping line: **73/23** (seed-1 ×3, receipt on PR #53's frozen branch) and
**74/29** (seed-2, `reports/s38-seed2-fresh/`, merged).

Reviewer-side gate — a report without the four stamps is refused:

```
python3 tools/validate_report.py --strict --data data reports/<your-report>.json
```

## 5. Run the tests

```
python3 -m unittest discover -s tests
```

Full suite ≈9 min. **Wants ≥2 GB free RAM** — on a small box, close other
servers first; running it concurrently with the webapp thrashes the machine.
Latest full receipt: 26/26 PASS on PR #71 branch `872cac7` (includes the
20-check bundle test).

## 6. Run the webapp (dev)

```
python3 webapp/server.py --port 8421 --host 0.0.0.0 --suites data
```

Open `http://127.0.0.1:8421`. `/api/health` reports fonts + git commit —
**fonts must not be 0**; a red font chip means the machine has neither system
faces nor the bundled fallback (bundled `fonts/` ships with PR #71).
Screen-share button uses `getDisplayMedia` (browser picker) and requires a
secure context: `127.0.0.1` works; LAN-IP or `file://` will be blocked by the
browser — that is the browser's rule, not ours.

## 7. Build the downloadable app (PR #71 branch)

```
python3 app/build_bundle.py --release    # needs GITHUB_TOKEN in env; zip = Release asset
```

Produces `dist/superocr-app-<sha>.zip` (≈3.3 MB) and uploads it to a GitHub
Release. `version.txt` stamps HEAD — **always rebuild after the final
commit/rebase**. The bundle self-tests on first launch: 12 demo items must
reproduce their build-time reads exactly or it fails loud (that is drift
detection, not decoration).

## 8. Contributing (collective protocol, short form)

Coordination happens in `dreamer2664/chatcode` (tasks, votes, bus); code
happens here.

1. Claim exactly one task (`chatcode tasks`), announce on the bus.
2. Branch: `agent/<name>/<task-id>`. Small PRs, additive where possible.
3. Before **every** PR: `bash tools/preflight-pr.sh <branch>` (branch must be
   pushed first; it checks you're not behind main).
4. Quorum of two votes per PR (`chatcode vote <task> accept-inspected
   --reason "…"`) — **never vote on your own work**; every review names the
   head sha it covered; second ballots are mechanical 15-minute checks, not
   re-reviews.
5. Receipts or it didn't happen: commit the report JSON the claim quotes.

## 9. Honesty rules (non-negotiable)

- A true 92 with a gallery beats a rounded 95.
- **Selection effect**: accuracy on clean/hand-picked items does not transfer
  to the suite. Measure on the full canonical suite or don't quote it.
- **Winner's curse**: if you swept variants, the best one is inflated —
  validate on a held-out seed (that's what seed-2 / S38 are for) before
  shipping any claim.
- Name both hard numbers (seed-1 **and** seed-2) in any generalization claim.
- Negative results are deliverables: a NO-SHIP receipt with committed rows
  (see `reports/s51-clahe.md`, PR #70) closes a direction for everyone and
  saves the next person a week.
