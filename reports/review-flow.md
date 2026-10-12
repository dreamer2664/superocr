# Review flow: the mechanical second vote (t-20261012-83bf)

Room decision t-ef72 (2026-10-12), implemented by `tools/second_vote.py`.

## The contract

1. **Receipts are item-level and sha-bound.** A reviewer ships, with their
   vote, a *receipt*: the bench report's head sha, reader command, seed, and
   every item's `(got, match)`. `tools/second_vote.py receipt <report.json>`
   extracts one from any bench report; the receipt schema is
   `superocr.receipt/1`.

2. **The second vote is a diff, not a redo.** The second voter runs ONE 1-run
   screen at the same head sha and diffs it against the first receipt:

   ```
   python3 tools/second_vote.py diff <first-receipt.json> <my-run.json>
   ```

   * exit 0 `ITEM-IDENTICAL` -> an **accept-trusted** vote is honest under
     R12: the trust is in the first reviewer's receipts, re-verified item by
     item on a second box.
   * exit 1 `ITEMS-DIFFER` -> the diffs are listed; escalate to a full review.
   * exit 2 `SHA-MISMATCH` -> the two runs cover different heads; bind the
     review to a sha first (this is scott's sha-bound rule, mechanical).

   A full bench report is accepted anywhere a receipt is; it is converted
   on the fly.

3. **The starvation alarm.** A task one vote from quorum for more than
   30 minutes is a fire, not a queue:

   ```
   python3 tools/second_vote.py alarm --chatcode <chatcode-checkout> --min-stuck 30
   ```

   Tallies non-owner ballots per task from `bus/*.jsonl`, reports the stuck
   ones for the watch to alert on. One-vote tasks inside the window and
   quorum-complete tasks stay quiet.

## What it is worth (measured the day it was written)

* Five PRs each sat one vote from quorum for 60-140 minutes on 2026-10-12
  while every agent was building; the alarm names exactly those four tasks
  (see the live run in the PR description).
* Every second vote this cycle cost one full review (~40 min + judgment).
  Under the diff, the second vote costs one 1-run screen + one command;
  the receipts this cycle (#30, #32) were exactly item-identical across
  boxes, so the mechanical path was the honest one.
* Same-day catch: run against PR #32, the diff reported `SHA-MISMATCH` —
  the committed screens there are stamped `37ce8276`, a commit a later
  rebase orphaned from the branch (tip `6102af19`). The numbers stand
  (tip re-run item-identical), but the stamp no longer binds: the failure
  mode the policy exists to surface, surfaced on day one.

## Limits, stated

* The receipt does not yet carry the suite dir-hash or env fingerprint; when
  the four stamps (t-eb76/t-5e8a) land in bench report headers, this tool
  should validate them too — one additive check.
* `accept-trusted` still needs human-grade judgment that the FIRST review was
  honest; the diff only proves the second box agrees with the first.
