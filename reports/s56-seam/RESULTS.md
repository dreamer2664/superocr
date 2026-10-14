# S56 topology-seam diagnostic — measured NO-GO

Experiment source `19b5f171d937cce8c56d481017b36b117f95d859`; preregistration `4380795`.
Owner Achilles; task t-20261013-9326. Diagnostic-only. No production reader, baseline, lex route, model weights, or canonical suite change.

## Scope and controls

A row-varying 4-neighbour minimum-edge-cut on the unchanged ink mask partitions every pixel losslessly. This is not S8/S10c straight-column search, classifier-confidence gating, morphology, adaptive thresholding, or a width-window grid. Ten geometry tests prove exact DP energy against exhaustive enumeration, a curved corridor that no straight column can separate, bridge partition, H-bar rejection and invariants. Four interface tests prove S54 source xyxy/+3px/H32 joint crop output, detected spaces (not truth), matched no-action arms, equal source cap. Optional glyph offsets are explicitly None; no word model is trained.

Parameters were fixed before any generated-data run; no tuning or retuning. Dev seed56003131 and heldout56004141 each contain24easy+24hard, with12hard families balanced2each. Additional18S53-style truth-box controls per split are ORACLE ONLY. Canonical seed1/seed2 were not read or regenerated. Development/heldout image-hash intersection=0.

## Exact-phrase outcomes — independent generated panels, NOT canonical

| Panel | Split | n | CNN seam OFF | Seam ON | Shipping lex | Recoveries / losses / net vs CNN OFF | Recoveries / losses / net vs shipping |
|---|---|---:|---:|---:|---:|---|---|
| development | easy |24|2|4|12|3 / 1 / +2|2 / 10 / -8|
| development | hard |24|2|2|8|0 / 0 / +0|0 / 6 / -6|
| heldout | easy |24|5|5|18|1 / 1 / +0|0 / 13 / -13|
| heldout | hard |24|2|1|8|0 / 1 / -1|0 / 7 / -7|

The matched CNN OFF→ON comparison isolates this seam intervention; the shipping comparison changes segmentation AND classifier, so its losses must NOT be attributed entirely to seams. No wrapper routes failed images to the seam method or claims shipping recoveries.

**Held-out matched result:** easy one recovery/one regression/net0; hard zero recoveries/one regression/net−1. Easy recovery `easy-easy-0008`; easy loss `easy-easy-0011`; hard loss `hard-strippy-0001`. Against actual shipping: zero held-out recoveries,13easy+7hard losses,net−20. Therefore **NO-GO**, no shipping proposal and no canonical3x/seed2 receipts invoked to rescue it. A dev-only +2 easy gain did not generalize.

## Per-family recoveries/regressions

|Panel|Split/family|n|CNN OFF|Seam ON|Shipping|R/L/net vs CNN|R/L/net vs shipping|Accepted seams|
|---|---|---:|---:|---:|---:|---|---|---:|
|development|easy/easy|24|2|4|12|3/1/+2|2/10/-8|33|
|development|hard/collage|2|0|0|0|0/0/+0|0/0/+0|1|
|development|hard/corrosion|2|0|0|0|0/0/+0|0/0/+0|2|
|development|hard/cross-shadow|2|0|0|0|0/0/+0|0/0/+0|3|
|development|hard/cut|2|1|1|1|0/0/+0|0/0/+0|0|
|development|hard/dark-on-dark|2|1|1|2|0/0/+0|0/1/-1|0|
|development|hard/darts|2|0|0|0|0/0/+0|0/0/+0|2|
|development|hard/obstruction|2|0|0|0|0/0/+0|0/0/+0|0|
|development|hard/snow|2|0|0|2|0/0/+0|0/2/-2|6|
|development|hard/spiderweb|2|0|0|0|0/0/+0|0/0/+0|0|
|development|hard/split|2|0|0|2|0/0/+0|0/2/-2|2|
|development|hard/stitch|2|0|0|1|0/0/+0|0/1/-1|5|
|development|hard/strippy|2|0|0|0|0/0/+0|0/0/+0|5|
|heldout|easy/easy|24|5|5|18|1/1/+0|0/13/-13|51|
|heldout|hard/collage|2|0|0|0|0/0/+0|0/0/+0|1|
|heldout|hard/corrosion|2|0|0|0|0/0/+0|0/0/+0|4|
|heldout|hard/cross-shadow|2|0|0|1|0/0/+0|0/1/-1|2|
|heldout|hard/cut|2|0|0|1|0/0/+0|0/1/-1|1|
|heldout|hard/dark-on-dark|2|0|0|2|0/0/+0|0/2/-2|0|
|heldout|hard/darts|2|0|0|0|0/0/+0|0/0/+0|1|
|heldout|hard/obstruction|2|0|0|1|0/0/+0|0/1/-1|1|
|heldout|hard/snow|2|0|0|1|0/0/+0|0/1/-1|1|
|heldout|hard/spiderweb|2|0|0|1|0/0/+0|0/1/-1|0|
|heldout|hard/split|2|0|0|0|0/0/+0|0/0/+0|10|
|heldout|hard/stitch|2|1|1|1|0/0/+0|0/0/+0|2|
|heldout|hard/strippy|2|1|0|0|0/1/-1|0/0/+0|15|

## Count proxies (not truth-box alignment or accuracy)

|Panel|Split|Correct glyph count OFF→ON /24|Correct word count OFF→ON /24|Accepted seams|
|---|---|---|---|---:|
|development|easy|4→10|20→20|33|
|development|hard|7→6|8→8|26|
|heldout|easy|10→11|21→21|51|
|heldout|hard|5→3|12→12|38|

The word grouping is inherited unchanged: this probe splits glyph pieces, not fused words, and cannot repair discarded/destroyed ink or a failed text-band mask. Source glyph cap128 was never reached. Count correction can still make identity worse. A successful synthetic H rejection does not validate all real single-letter topologies.

## Runtime and separate ORACLE controls

|Panel|CNN OFF median ms|Seam ON median ms|Shipping lex median s|Oracle raw /18|Oracle +lex /18|
|---|---:|---:|---:|---:|---:|
|development|5.756|16.287|1.666|4|9|
|heldout|5.211|15.802|1.696|2|4|

Batch182.9s serialized, OPENBLAS_NUM_THREADS=1. Reported arm timings cover segmentation+classifier+lex, not shared ink_mask preprocessing, interface crop metadata, process startup, or S53 oracle generation. Shipping timings are in-process baseline.read_text+fix_line, the exact reader_lex operations but NOT per-image CLI process costs. First dev image includes cold template initialization; heldout is warm. This is not a shipping latency benchmark.

Oracle numbers are full-PHRASE exact on independent18-item S53-style panels with injected truth boxes and spaces; they are not Cormac’s S54 word-exact metric, not reader results, not canonical results, and not a mathematical upper bound. Model glyphcnn-v7b stays frozen; classifier/domain limitations remain.

## Reproduce and inspect

```sh
OPENBLAS_NUM_THREADS=1 python3 tests/test_s56_topology_seam.py
OPENBLAS_NUM_THREADS=1 python3 tests/test_s56_probe_interface.py
OPENBLAS_NUM_THREADS=1 python3 tools/s56_seam_probe.py --out reports/s56-seam --data /tmp/s56-independent
```

JSON receipts contain all per-item labels, reads, times, detected word-crop hashes, accepted seam paths, geometry proxies, recoveries/losses and independent image/manifest/model hashes. The output data directory contains newly generated independent PNGs; it never regenerates a canonical evaluation suite. Exact runtime/font versions and code hashes: run-metadata.json. The batch was run at19b5f17; subsequent report/interface-test additions do not change experimental code (hashes recorded).

## Decision / handoff

**Diagnostic complete, NO-GO.** Publish for independent review/closure, not production integration. No self-vote. Cormac’s published contract is implemented; live ACK/collage corpus decision remains coordination-only and is not falsely claimed received. Differential word-rotation/collage is absent from S53 oracle controls but present in both generator hard panels (2items each). Do not create a duplicate word-model/corpus lane or silently reopen this failed setting. Goals98/95 remain unmet.
