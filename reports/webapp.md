# superocr web dashboard (t-20261013-c395)

Browser UI for superocr, replacing the terminal for demos, suite browsing, and
floor monitoring. Carlo's directive via pericles 2026-10-13 08:51Z. Extends
the S4 demo (`tools/demo_server.py`, which stays untouched) into a full
single-page app.

## Run

    python3 webapp/server.py --port 8421 [--host 0.0.0.0]
        [--suites /path/suiteA,/path/suiteB]
        [--bus-dir /path/chatcode/bus] [--board-dir /path/chatcode/board/tasks]

Then open http://localhost:8421. stdlib + numpy/Pillow only; no CDN, no
frameworks, no network calls from the page — works from a clean clone offline.
Suite/bus/board dirs are optional; the matching tabs show a hint when absent.

## What it does (task scope, item by item)

1. **Live OCR results display** — `Live OCR` tab. Screen share
   (`getDisplayMedia`), webcam, or file drop. Every read POSTs a PNG to
   `/api/ocr`, which runs the SAME shared path as the CLI typer
   (`typer.recognise -> reader.read_chain`) — the web app is a window on the
   pipeline, not a parallel OCR. Each result row carries `server_ms`
   (recognition alone, measured server-side) and `e2e_ms` (browser round
   trip). Rolling history keeps the last 200 reads.
2. **Suite progress dashboard** — `Suites` tab. Picks up `--suites` dirs
   (each holding `<split>/manifest.jsonl` + images). Browse items with
   rendered image next to the true label; per-item `OCR` button runs it and
   stamps EXACT/MISS with the got-text and server_ms; `Probe next 10` walks
   un-probed items sequentially with a progress bar and a running exact-count.
3. **Agent activity feed** — `Tasks` tab, lower half: last 200 bus messages
   grouped by sender with each agent's most recent line and timestamp.
4. **Bus message viewer** — `Bus` tab: channel picker (every `*.jsonl` in
   `--bus-dir`), tail 50/100/300, optional 5 s auto-refresh, type-colored.
5. **Screen overlay capability** — drag a box on the shared-screen video to
   select the region to read; the overlay floats the latest read (text,
   family, confidence, ms) over the video and re-reads the region on the
   chosen interval (0.5/1/1.5/3 s or manual). The crop happens client-side on
   a canvas at video-native resolution; the server never sees the full screen.

Also: `Bench reports` tab — parses every bench receipt in `reports/*.json`
(run_id, reader, seed, sha, easy/hard vs bars, PASS/FAIL), click a row for the
raw JSON.

## API

| endpoint | notes |
|---|---|
| `GET /api/health` | version, git sha, model files, enabled features |
| `POST /api/ocr` | `{image: base64, family?, detail?, route?}` → `{text, family, avg_confidence, server_ms, route, text_raw?, confidences?}`; route `typer` (default) = the S4 demo path (`T.recognise`), route `lex` = the SHIPPING bench route (`baseline.read_text` + `lex_projection.fix_line`, the reader_lex 73/21 receipt path; `family` ignored on purpose — the bench runs bare); `text_raw` present when the lex projection changed the read; 400 bad payload/route, 413 >4 MiB, 422 reader-refused |
| `GET /api/suites` | suite dirs + splits + family counts |
| `GET /api/suite-items?suite=&split=` | `{id,label,family}` list |
| `GET /api/suite-image?suite=&split=&id=` | PNG bytes + `X-Item-Label` header |
| `GET /api/reports` / `GET /api/report?file=` | receipt summaries / raw |
| `GET /api/bus?channel=&limit=` | bus tail (needs `--bus-dir`) |
| `GET /api/tasks` | board tasks + status counts (needs `--board-dir`) |

Path traversal is blocked on every file-serving route (`resolve()` +
`is_relative_to`, `/static/` reduced to `Path(...).name` + suffix allowlist).

## Tests

`tests/test_webapp.py` — 11 tests, fast/offline/seeded: real HTTP against an
ephemeral-port server with tmp fixtures (2-item generated suite, 3-message
bus, 2-task board). The OCR test asserts response shape/timing, not
recognition correctness (correctness has its own benches; a dashboard test
must not flake on a hard seed). Error paths covered: bad base64 (400),
not-an-image (400), >4 MiB (413, body drained so the client gets a clean
status), suite/report traversal (404), unknown route (404).

    python3 -m pytest tests/test_webapp.py -q   # 11 passed, <3 s on the dev box

## Routes (W1, t-20261013-9252)

The demo-inherited `typer` route and the shipping `lex` route are DIFFERENT
readers: measured on easy seed 42, `baseline.read_text` gives
`SwiR hJnnel Hdge 6int otter` while `T.recognise` gives
`SwR kHHo1 HdQo HHt oHou`. The bench receipts (73/21, 3× on canonical seed-1)
bind to `baseline.read_text + fix_line` — so any demo-quality claim must use
`route=lex`. The UI exposes the choice; default stays `typer` for continuity
with the S4 demo.

## Latency honesty

The demo's 10 s bar (JOBS.md S9) applies to the same `recognise()` call this
server makes; `tools/demo_latency.py` remains the latency receipt harness for
the S4 endpoint. For the webapp, every response carries its own measured
`server_ms`, so any claim about the UI path can be re-measured from the
history table in-page. A dedicated webapp latency receipt (median over N
reads through the browser path) should be generated before any demo claim —
tracked as a follow-up, not asserted here.

## Limits, named

- `getDisplayMedia` needs a secure context (https or localhost) and a user
  gesture; on a plain-http LAN address browsers will refuse screen share —
  webcam and file drop still work. This is a browser rule, not a server one.
- The page has no authentication; it binds whatever `--host` says. Run it on
  a trusted network or localhost.
- Suite probe reads are sequential single-threaded by design (latency honesty:
  parallel reads would contend and inflate every server_ms).
