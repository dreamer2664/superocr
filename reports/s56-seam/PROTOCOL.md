# S56 — bounded topology-seam probe (t-20261013-9326)

Owner Achilles. Base a530a8ffb059d48dd1ac4a2204dc852cc143dd45.
W2 package build is finished and externally review-gated (PR82); this is the
ONLY active experiment. No production baseline/reader/lex change.

## New falsifiable mechanism, not a reopened lane

Read S43 taxonomy and CLOSED S8/S10c template/CNN vertical-cut probes first.
Those enumerate straight columns and accept by matcher probabilities/width.
This probe instead finds a **row-varying minimum-edge-cut seam** in an unchanged
binary mask. Horizontal foreground adjacency and vertical adjacency crossed
by a one-pixel seam step form the cost; a 0.05 step penalty makes ties stable.
Assign EVERY ink pixel to exactly one side: no morphological edit, deletion,
adaptive/CLAHE preprocessing, classifier-confidence acceptance, or size-window
sweep. Curved separation can recover overlapping projections that NO straight
column can isolate. A synthetic curved-corridor control must prove that novel
mechanism before evaluating OCR. A thick H crossbar must NOT be accepted.

Frozen geometry gates (not selected on canonical labels): each side >=15% of
parent ink and >=75% of its height; crossed ink edges <=max(1,floor(.06*height));
one split per parent, no recursion. Reject parent dimensions below2 or above
256x1024. Maximum128 source glyphs per image, with cap recorded for BOTH arms.
These are conservative hypothesis parameters, NOT a claimed optimal setting.

## Interfaces and controls

Cormac's published S54 tools/s54_word_crops.py contract at aefcc69:
source mask readers.segmentation.ink_mask; inclusive word bbox+3px context;
joint BILINEAR scale to height32, aspect preserved; optional glyph offsets.
Read-time output must use detected boxes, NEVER labels/truth boxes/counts.
Explicit source-coordinate format xyxy (S53 truth boxes are x0,x1,y0,y1;
conversion is named at the oracle boundary). No deskew on either arm, so
returned source boxes and crop coordinates remain aligned.

Primary paired comparator: same existing projection glyph_boxes and frozen
v7b classifier + same lex postpass on both arms, seam OFF vs ON. Baseline is
NOT the shipping reader. Secondary comparator: actual baseline.read_text +
fix_line (reader_lex-equivalent) on exactly the same images. A gain over the
weaker CNN comparator is NOT a shipping gain. Exact-phrase and word-count/glyph
count proxies are distinct; no case folding in exact accuracy.

Truth-box v7b control uses generated S53-style data ONLY and is clearly labeled
ORACLE, not read-time segmentation, canonical accuracy, or a mathematical
upper bound (alternate contexts can change classifier opinions).

## Data separation fixed before runs

- Development: independently generated easy24+hard24, seed56003131, hard family
  cycling in existing generator order; plus18 S53-style truth-box controls,
  corpus_id=s56-development, same seed. Development can debug implementation,
  not select against canonical labels. No parameter grid is planned.
- Held-out: independent easy24+hard24, seed56004141; plus18 S53-style oracle
  controls, corpus_id=s56-heldout. Exact fixed mechanism evaluated once after
  development invariants pass; no retuning on this split.
- Canonical seed1 and seed2 (b2c460d2/ec64cd63) are evaluation-only and NOT read,
  regenerated, or tuned on in this bounded first diagnostic. No fresh canonical
  result or shipping change is proposed. Any future shipping candidate needs
  three FULL canonical easy/hard lex receipts, zero easy regression, and separate
  seed2 evaluation. This experiment cannot waive that gate.

## Receipts and decision

Publish SHA/command/runtime, generated manifest and image hashes, every item's
family/GT/arm reads, exact recoveries/regressions/net vs BOTH comparators,
accepted seams and count proxies, matched-arm runtime, separately named oracle
results, and dev/held-out per-family tables in reports/s56-seam/.
NO-GO if no held-out exact gain over shipping or any easy regression; even a
positive bounded result is diagnostic-only, never shipping acceptance. Honest
negative result is valid. Goals98/95 remain unmet;30 fixes is not promised.

Reproducible planned command:
`OPENBLAS_NUM_THREADS=1 python3 tools/s56_seam_probe.py --out reports/s56-seam --data /tmp/s56-independent`

Checkpoint protocol is pushed BEFORE running the batch. No model is trained;
existing v7b weights stay frozen, production paths and suite recipes untouched.
