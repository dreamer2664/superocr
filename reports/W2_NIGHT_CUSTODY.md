# W2 night release custody — Achilles

Original implementation: Marcus, PR71 a8f2edd881391f50c8968afe4d51d39a7b81ca57.
POSIX launcher correction: Brasidas, PR80 35057484911c1377fa628e14cb3183b7ac07f856.
Custody does not transfer authorship. This branch retains both original commits.

## Independently inspected checkpoint

On the exact PR80 head, Achilles ran:

- `python3 tests/test_app_launcher.py`: 24/24 PASS.
- `python3 tests/test_app_bundle.py`: all 20 checks PASS, 42.1 seconds.
- The new launcher fixture extracted and applied to original PR71's launcher:
  24 checks, four failures, expected exit 1. No original source was changed.

Receipts: `reports/w2-night/`. Structured independent PR80 votes are
Achilles #503d380a and Leonidas #1fbc0ebd on t-20261013-f43a.
These approve only the small correction, NOT final W2 release custody.

## Custody changes

Packaging only: store full commit SHA in version.txt; clarify historical
73/23 accuracy, self-test reproducibility rather than accuracy, and unshipped
S55 proposal. Remove the incorrect claim that first-run drift is normal.
Add a full-commit provenance assertion to the bundle test. No baseline,
production reader, lex route, or canonical-suite change.

## Bounded next verification

Re-run launcher and bundle tests on this branch. Build the default 12-item
bundle; isolate a fresh Python virtual environment (no system site-packages),
unzip outside the repository, compare full archive SHA256 and every shipped
source/font hash, run both-route selftest, deliberately tamper expectations
and confirm exit 1, and live-smoke the shipping `lex` route. Record source SHA,
Python/numpy/Pillow versions, 8 bundled font hashes/license, execution times,
GT accuracy separately from reproducibility, and clean-room limits.

Do not replace historical release assets. New release/download roundtrip only
after approved staging; unique tag/source SHA. The final review head and exact
package hash will be sent to Barry and Leonidas for independent non-owner
structured ballots on t-20261013-135d. Achilles cannot approve own custody.

## Explicit limits

This is a Linux/POSIX environment. No native Windows/macOS execution or actual
browser screen-picker interaction is claimed. Static getDisplayMedia wiring
is not an interaction receipt. 98% easy / 95% hard goals remain unmet.
`reports/app-bundle.md` is Marcus's historical report, not a fresh night test.
A passing bundled selftest can reproduce wrong reads; it is not an accuracy bar.
