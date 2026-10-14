# superocr CAPTCHA Studio

A local synthetic-text generator and **honest shipping-route OCR tester**.
Generate reproducible degraded images, see the exact ground truth, inspect
oracle label boxes, read pixels through the existing OCR route, and export
PNGs + labels + provenance as a ZIP. There is no external OCR service.

**This is a review-candidate app, not a claim that OCR meets 98% easy / 95% hard.**
The current recognition system makes substantial errors; mismatches remain visible.

## Downloaded bundle: unzip → start → browser

Requires **Python 3.10+**. First setup needs internet access to install NumPy 2.x
and Pillow 12.x if suitable versions are not already installed. Python itself is
NOT included. This is a Python app bundle, **not a signed/native .exe or .app**.

- **Windows:** double-click `start.bat`, or run `py -3 launch.py` in the folder.
- **macOS:** run `sh start.command` in Terminal (or open the executable launcher).
- **Linux:** `sh start.sh`.
- Open **http://127.0.0.1:8488** if the browser does not open automatically.
- Keep the terminal open. Press **Ctrl+C** to stop; the watchdog will not restart
  after an intentional interrupt.

The launcher verifies all eight bundled fonts, exercises all 18 generation
arms, repeats the generation to check determinism, and checks ZIP export BEFORE
starting. A failing selftest stops startup with a nonzero status and clear error.
Unexpected server exits are logged in `studio.log` and retried at most twice.
This is not a health/hang monitor and does not imply an always-running AI agent.

Options:

```text
python3 launch.py --port 8489 --no-browser
python3 launch.py --no-install
python3 launch.py --max-restarts 0
python3 apps/captcha-studio/server.py --selftest
python3 apps/captcha-studio/server.py --selftest --with-ocr
```

`--skip-selftest` exists for diagnostics, prints a warning, and is not recommended.
If dependencies are missing, you may install them yourself with
`python3 -m pip install -r requirements.txt`. The bootstrap otherwise creates
an isolated `.venv` when needed. An occupied port or missing Python produces an
error; it is not called a successful launch. See `studio.log` for child output.

## Source checkout

```bash
python3 apps/captcha-studio/server.py --selftest
python3 apps/captcha-studio/server.py --browser
python3 tests/test_captcha_studio.py
python3 tools/build_captcha_app_zip.py --out /path/to/fresh/output
```

From source, `python3 apps/captcha-studio/launcher.py` is the bootstrap equivalent
of the bundle's root `launch.py`. Official builds refuse a dirty source tree;
`--allow-dirty` emits an explicitly marked development bundle for testing.

## Controls and exported data

- Families: corrosion, rotation, spiderweb, cross-shadow, strippy, darts,
  combined effects, clean controls, or the 18-arm sampler.
- Severity is family-specific. Seed and sample index determine the random stream.
- A batch contains 1–32 images. Custom text supports ASCII letters, digits and
  spaces, up to 48 characters, preserving case and interior spaces.
- Blank custom text uses the existing seeded mixed-case vocabulary generator.
- Export includes `images/*.png`, `manifest.jsonl`, `provenance.json` and a README.
  Labels are exact; each row carries its seed/index/effects, dimensions, PNG hash,
  and oracle character geometry. Oracle boxes are NOT the reader's segmentation.
- Same recipe/seed/index/text and font/library versions reproduce the sample.
  Font hashes and core-source hashes are included in provenance. Do not assume
  byte-identical pixels across different FreeType/Pillow/NumPy implementations.
- Only the latest 128 images are retained, in memory. Export before closing or
  generating many more batches. Expired IDs return a clear 404; no disk dataset
  is silently written or uploaded.

## Frozen S53 and OCR integrity

The original `generator.py` and `tools/gen_hard_corpus.py` are unchanged. This
isolated adapter reuses their base-rendering/degradation functions. The studio's
selectable/custom-label recipe is deliberately named **g1-studio-v1**, not the
frozen S53 corpus. Combined effects rotate last. Existing corpus manifests and
canonical evaluation suites are not read, regenerated, edited, or used for tuning.

Eight licensed DejaVu faces are bundled with their license/hash manifest. The
studio sets the original font search list to those same eight faces **in this
process only**; no core source file is patched. This makes the app work without
system fonts and preserves deterministic face order.

OCR receives **PNG bytes only**. It calls the unchanged
`baseline.read_text(image, None)`, then `tools/lex_projection.fix_line`; this is
`reader_lex`, not `typer`, an oracle, or a lookup of the expected label. The
existing v2 tie-break model is included. Experimental piece-policy overrides
are disabled for this route. Comparison with ground truth happens afterward,
without stripping, case folding, or fuzzy credit. Matcher confidence is NOT a
calibrated probability. Custom words outside the shipped vocabulary may be
changed by lex projection; raw baseline output is shown separately.

First OCR use warms templates and can take a minute. OCR requests are serialized;
a concurrent request receives a busy response rather than starting another model.
A selected/generated batch is not a frozen benchmark or unbiased accuracy study.

## Privacy and network use

Default binding is loopback only. JSON body/image-count/text limits and strict
same-origin checks protect the local interface from ordinary cross-origin browser
requests. Static paths are allowlisted; there is no arbitrary-file API or URL fetch.
No credentials, user directories, corpora, reports, caches or virtualenvs are in
the downloadable package: the builder uses an explicit file allowlist.

For an Arena/trusted development preview only, use `--host 0.0.0.0 --port 8488`.
That exposes an **unauthenticated** service to the accessible network. Do not use
it as a public multi-user production service. The app accepts same-origin proxy
hosts and uses relative browser URLs, never browser-side localhost API calls.

## Verification boundaries

Linux automated receipts cover deterministic generation, all arms, validation,
exports, missing/tampered font detection, API error paths, label-isolated OCR,
launcher status/watchdog behavior, and a clean extracted bundle smoke.
See the current PR and committed receipt for which commands actually ran.
Native Windows/macOS execution and OS/browser screen capture are **not** claimed.
Screen capture belongs to the separate W2 application; this generator is additive.

Fonts: `apps/captcha-studio/fonts/LICENSE_DEJAVU.txt`.
Build stamp and allowlisted file hashes: `studio-build.json` in a bundle.
