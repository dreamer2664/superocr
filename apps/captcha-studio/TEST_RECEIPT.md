# G1 / t-20261013-5aed — pre-publication verification

Owner: Brasidas, covering Barry by Carlo's night-shift directive. Duplicate task
`t-20261013-acb0` is consolidated here, not a parallel implementation.

## What was actually checked

- `python3 tests/test_captcha_studio.py`: **24 tests PASS**, 10.046 seconds in the
  recorded final source run (nested family/severity subtests included).
- All 18 S53 mechanism/severity arms exercised; repeated PNGs, labels, boxes and
  deterministic export agree within this environment.
- Correct font hashes/order and no system-font lookup requirement; a corrupted
  font fails before startup. The eight font assets retain their license.
- HTTP validation, strict label-free OCR request, path allowlist, cross-origin
  rejection, proxy-host same-origin acceptance, busy/cache/expired-ID controls.
- A deliberately incorrect reader stays incorrect: expected labels are never
  passed to the reader or substituted for its output.
- Child exit 7 remains 7 through logging; failing selftest prevents startup;
  explicit skip is warned; clean exit does not restart; restart budget is bounded.
- Clean-room allowlisted ZIP built and run from outside its source directory.
  Full quick selftest passed with **8 fonts / 18 arms / deterministic / export**.
  Real shipping-route smoke read `amber` as `amber` (3.367 seconds in the initial
  extracted-bundle smoke). This is execution evidence, not benchmark accuracy.
- Playwright Chromium on Linux: initial six thumbnails; custom `Amber 42`;
  oracle overlay aligned; real OCR returned `Amber 42` (3.360 seconds); the
  browser request contained only an image ID; ZIP downloaded and manifest/PNG
  hash checked. Desktop 1440 px and mobile 390 px: no horizontal mobile overflow,
  no page/console errors. Screenshot: `docs/preview.png`.
- Python compilation and JavaScript syntax checks passed. Core source files are
  unchanged relative to base `a530a8ffb059d48dd1ac4a2204dc852cc143dd45`.

Environment: Linux, Python 3.13.16, NumPy 2.3.5, Pillow 12.3.0. Runtime provenance
also records FreeType, zlib, font digests and core source hashes.

## What this does NOT establish

No full 200-item / three-run accuracy benchmark was rerun for this additive app.
No 98/95 acceptance, native Windows/macOS execution, OS screen-picker interaction,
or production/public-network hardening is claimed. The initial standalone build
was explicitly `-dev`; a clean committed-source candidate gets its own immutable
build stamp/hash and clean-room retest. Independent reviews are still required;
this is not a self-approval or permission to merge.

## Reproduce

```bash
python3 tests/test_captcha_studio.py
python3 apps/captcha-studio/server.py --selftest --with-ocr
python3 tools/build_captcha_app_zip.py --out /absolute/fresh/output
# unzip elsewhere; then run the bundled server's --selftest --with-ocr
```

The source app reuses S53 functions but has its own `g1-studio-v1` recipe
(selectable/custom labels, combined effects rotate last). No frozen corpus recipe,
manifest or canonical evaluation input was modified. The shipping function path
is the existing baseline with `family=None`, then existing lex projection; the
bundled font search order is configured in-process, not by patching core files.
