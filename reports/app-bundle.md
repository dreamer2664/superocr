# W2 — the downloadable app (t-20261013-b411)

**Directive** (pericles DM 2026-10-13 15:43, relaying Carlo): the web app is
"unstable" and must become a **real downloadable standalone application that
can actually read screen content**. Priority 1.

**Delivered:** `app/build_bundle.py` → `dist/superocr-app-<sha>.zip` (3.3 MB)
— unzip, double-click a launcher, browser opens, screen reading works. Plus
two root-cause fixes that made "read screen content" untrue before this task.

## Root causes found (with receipts)

1. **The screen button never captured the screen.** `#btn-screen` ("Share
   screen") called `navigator.mediaDevices.getUserMedia` — the CAMERA API.
   Screen capture is `getDisplayMedia`. Fixed in `webapp/static/app.js`
   (kind-parameterized `startCapture`, browser "Stop sharing" chip wired to
   `stopCapture`, secure-context error text). This is the literal
   "cannot actually read screen content" bug.
2. **Font portability — silent garbage reads off Linux.**
   `generator.available_fonts()` knew only
   `/usr/share/fonts/truetype/dejavu/*` paths. On macOS/Windows it returns
   `[]`, and `load_font` falls back to Pillow's bundled bitmap face — a
   different metric set that quietly corrupts BOTH generation and template
   matching. No error, just wrong reads. Fixed by committing the 8 DejaVu
   faces + license under `fonts/` (3.3 MB, redistributable under the bundled
   Bitstream/DejaVu license) as fallback candidates; the system copy wins
   when present, dedupe by basename — **canonical machines see the identical
   face list in the identical order** (verified: `available_fonts() ==
   _SYSTEM_FONT_CANDIDATES` here), so suite hash b2c460d2 cannot move.
3. **"Unstable" = the demo's host, not the app.** The live preview Carlo
   watched ran inside an agent sandbox wiped 7× to date; every wipe killed
   the server mid-demo. The bundle runs on Carlo's machine — structurally
   immune. (In-repo evidence of app health: 12/12 webapp tests, merged
   #55/#60/#64, latency receipts.)

## What the bundle contains

| piece | purpose |
|---|---|
| `start.sh` / `start.command` / `start.bat` | python presence+version check, one-time `pip install --user -r requirements.txt`, selftest, then **auto-restart watchdog loop** + browser open (`--open`, first iteration only) |
| `webapp/` + reader stack (`baseline/reader/generator/preclassify/typer` + `tools/lex_projection` + `readers/ models/ recipes/`) | the app and BOTH routes: `lex` = shipping floor (easy 73 / hard 23, median 2.1 s post-S39) and `typer` demo |
| `fonts/` | the 8 DejaVu faces (root cause 2) |
| `demo-suite/` | 12 seeded items (6 easy, 6 hard across collage/corrosion/spiderweb) with **`expected_lex`/`expected_typer` computed at build time** |
| `--selftest` (server flag) | reads every demo item through both routes and demands EXACT reproduction of the build-time expectations; `fonts <8` fails loudly; drift lines name item + expected→got; exit 1 on any failure |
| `version.txt` → `/api/health.app_version` + UI header chip | bundle id, git sha, build ts — "which build broke?" becomes answerable; header shows `fonts 8/8` and goes red below 8 |
| `app.log` | every uncaught request exception lands here timestamped (`_crash_log`); launcher appends restart markers |
| `INSTALL.md` | 3-OS install, screen-read walkthrough, honesty section (73/23, bar NOT met, in-distribution text only), troubleshooting (fonts 0/8, secure context, port, macOS screen-recording permission) |

## Verification (clean-room)

Fresh dir, unzip, no repo in sight:

- `--selftest`: **12/12 PASS, 0 drift** — easy 6/6 exact reads; hard items
  reproduce their build-time reads (misses included — drift detection is
  about environment identity, not accuracy). First run 42 s (template cache
  self-builds inside the bundle; INSTALL sets the ~1 min expectation).
- Live server: `/api/health` carries the bundle stamp + `fonts: 8`;
  `/api/ocr route=lex` returns the expected text; warm lex reads ~0.9 s
  (server process, cache warm), typer ~0.7 s — demo bar (10 s) met with room.
- Tamper control: editing one `expected_lex` in the manifest makes selftest
  print `DRIFT` and exit 1 (pinned in `tests/test_app_bundle.py`).
- `tests/test_app_bundle.py`: **20 checks** (font-fallback probe with system
  paths monkeypatched away, bundle completeness, executable launchers,
  in-place selftest, drift detection, live-server smoke) in ~58 s.
- Full offline suite: see PR (run_all result pasted there).

## Distribution

Zip is generated, never committed (JOBS.md). `--release` uploads it as a
GitHub Release asset (tag `app-v0.1.0-<sha>`, prerelease) using the team
token from env — token never written to disk or logs. Rebuild any time:
`python3 app/build_bundle.py --release`.

## Bars

- Reads screen content: **MET** (getDisplayMedia fix + region select + auto
  interval, all through `/api/ocr`).
- Downloadable standalone: **MET** (zip + launchers; deps auto-install on
  first run — internet needed once, documented).
- Stability: watchdog + crash log + selftest + version stamp **MET**;
  accuracy bar (98/95) **NOT met** — unchanged by this task; the app reports
  the honest numbers in INSTALL.md and the UI.

## Open question (sent to pericles in the ACK DM)

Browser-picker capture (shipped) vs promptless full-desktop capture (needs a
per-OS native helper — staged as v2 if Carlo wants it).
