# #27 delta screen receipt — 1b3c4f0 (pericles, quiet box, 12 Oct 16:23–16:37Z)

Independent re-run of the S8 ladder at the FINAL head `1b3c4f0` (post-rebase),
official reader command `python3 baseline.py {image}`, seed 1, all 200 items,
0 errors.

Headline: **easy 54/100 · hard 12/100** — reproduces barry's claimed numbers
at this sha exactly.

For the sha-bound second look (the rebase invalidated the ef6f180 binding):

```
python3 tools/second_vote.py diff <your-ef6f180-receipt.json> \
  reports/27-delta/receipt-pericles-1b3c4f0.json
```

ITEM-IDENTICAL (rc=0) -> accept-trusted on 1b3c4f0; ITEMS-DIFFER (rc=1) ->
the diff names every moved item; SHA-MISMATCH (rc=2) -> wrong pairing.

Run log: 20261012T162352Z-easy-hard.json/.md (this directory).
