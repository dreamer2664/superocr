# S51 — CLAHE pre-step probe: measured, net-harmful, NO-SHIP

**Owner:** barry · **Task:** `t-20261013-03e8` · **Date:** 13 October 2026 (afternoon)
**Task text:** "Some families have very low contrast. Implement CLAHE (Contrast
Limited Adaptive Histogram Equalization). Test on all families."

## Verdict

CLAHE as a luminance pre-step is **net-harmful to the shipping route and must
not be wired.** On canonical seed-1, both clip settings lose more than they
gain: `clahe-2.0` turns hard 23/100 into **20/100** (−3), `clahe-4.0` into
**18/100** (−5); easy is exactly neutral (73 = 73 = 73). The family the task
names (low contrast → dark-on-dark) **does not improve** (3/8 → 3/8 → 2/8).
The six dead families do not move at all (all stay 0/8). What CLAHE does do
reliably is amplify occluders and background texture enough to break the
recoverable-with-structure families — obstruction collapses **4/8 → 0/8 →
1/8**. Close the contrast direction; it joins S23/S24/S26/S27/S28/S29 on the
measured-no list. The remaining route to the bar stays the v5 recognizer
lane (S30/t-6d08, cormac).

## Protocol (fixed up-front, before any numbers were seen)

- Arms: `off` | `clahe-2.0` | `clahe-4.0` — grid fixed at 8×8 tiles, 256-bin
  histograms, luminance only, output rebuilt as grayscale RGB.
- Implementation: hand-rolled numpy ([`tools/s51_clahe_probe.py`](../tools/s51_clahe_probe.py)).
  Repo constraint (stdlib + numpy/Pillow) means **no cv2**; standard CLAHE
  formulation (per-tile hist, clip at `clip × mean bin mass`, uniform
  redistribution of clipped mass, tile CDFs, bilinear interpolation).
  Deterministic: repeated calls return bit-identical pixels (asserted).
- Route: shipping wrapper semantics mirrored in-process
  (`baseline.read_text(img, None)` → `tools.lex_projection.fix_line`), byte
  semantics verified against `python3 tools/reader_lex.py {image}` in earlier
  receipts (s22-3x-settled, W1 screen).
- Data: canonical seed-1 suites, re-regenerated after the /tmp wipe, dir hash
  verified `b2c460d2fb5a8f83…` before a single read ran. Seed-2 untouched
  (S38 just consumed it as an independent screen; no tuning against it).
- Rows: all 600 item rows committed at
  [`s51-clahe-probe-rows.jsonl`](s51-clahe-probe-rows.jsonl)
  (suite, id, family, arm, label, got, exact, sec) + footer
  (`{"event":"done","rows":600,"wall_s":1307.3}`).

## OFF control (harness gate)

The `off` arm is required to reproduce the settled shipping line exactly or
the whole probe is void. It does: **easy 73/100, hard 23/100** — matching the
s22-3x-settled receipts (73/73/73, 23/23/23) read for read at the total
level; per-item misses also match the settled miss sets (checked during
analysis; flip enumeration below is relative to this `off` arm).

## Totals

| suite | off | clahe-2.0 | clahe-4.0 | Δc2 | Δc4 |
|---|---:|---:|---:|---:|---:|
| easy | 73/100 | 73/100 | 73/100 | 0 | 0 |
| hard | 23/100 | 20/100 | 18/100 | −3 | −5 |

## Family × arm (hard suite; easy is a single family and was neutral)

| family | off | c2.0 | c4.0 | note |
|---|---:|---:|---:|---|
| collage | 0/8 | 0/8 | 0/8 | unmoved (dead family) |
| corrosion | 0/8 | 0/8 | 0/8 | unmoved (dead family) |
| cross-shadow | 0/8 | 0/8 | 0/8 | unmoved (dead family) |
| darts | 0/8 | 0/8 | 0/8 | unmoved (dead family) |
| strippy | 0/8 | 0/8 | 1/8 | noise-level flip, not a rescue |
| cut | 5/8 | 5/8 | 5/8 | neutral |
| split | 3/9 | 3/9 | 3/9 | neutral |
| **dark-on-dark** | 3/8 | 3/8 | 2/8 | **target family: no gain, one loss at c4.0** |
| stitch | 2/9 | 3/9 | 3/9 | only consistent gain (+1 both) |
| snow | 5/9 | 6/9 | 3/9 | unstable (+1 then −2): clip-sensitive |
| spiderweb | 1/9 | 0/9 | 0/9 | −1 both |
| **obstruction** | 4/8 | **0/8** | 1/8 | **collapse — the dominant harm** |

## Item-level flips vs `off`

- **clahe-2.0:** gained `snow-0003`, `stitch-0007` · lost
  `obstruction-0000/-0004/-0005/-0006`, `spiderweb-0008` → net −3.
- **clahe-4.0:** gained `obstruction-0001`(!), `snow-0003`, `stitch-0007`,
  `strippy-0002` · lost `dark-on-dark-0001`, `obstruction-0000/-0004/-0005/-0006`,
  `snow-0005/-0006/-0008`, `spiderweb-0008` → net −5.

The gains concentrate in stitch/snow singlets; the losses concentrate in
obstruction almost wholesale. Mechanism reading: adaptive tile equalization
lifts local background/structure texture to ink intensity, so the binarizer
inherits occluder geometry — fatal for obstruction (gaps are the signal),
occasionally useful where segmentation is borderline (stitch). Snow's swing
between clip 2.0 and 4.0 is pure clip sensitivity, i.e. the transform trades
one brittle knob for another.

## Limits (honesty)

- One CLAHE formulation (L-channel, 8×8, clip {2.0, 4.0}); a colour-channel
  CLAHE or a finer clip sweep is not excluded from helping singlet families,
  but the direction-level conclusion — global pre-step on the shipping route —
  is what the task asked about and the answer is negative with margin.
- Single probe run (deterministic transform; repetition changes nothing —
  the reader and CLAHE are both bit-deterministic, as established by the
  s22-3x-settled item-diff-0 property plus the asserted pixel determinism of
  `clahe()`).
- Bench-scale costs: CLAHE itself adds ~0.5–1.5 s/item on this box; reads
  stay 1.5–2.5 s/class. Latency is not the reason for NO-SHIP; accuracy is.

## Recommendation

1. **Do not wire CLAHE** into the shipping reader (baseline or wrapper).
2. Mark the "low-contrast families" hypothesis tested-and-negative at the
   preprocessing layer; dark-on-dark's residue is a recognizer/segmentation
   problem, not a global contrast problem.
3. The +1 stitch gain is inside noise for one screen and one setting; not
   worth a family-conditional pre-step (would need its own held-out proof).
4. Keep the probe tool: future pre-step ideas (S4x-class) can reuse the
   OFF-control protocol — reproduce the settled line first, then compare arms.
