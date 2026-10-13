# S43 — Failure analysis: the 77 hard misses by root cause (t-20261013-7eff)

**Owner:** leonidas · **Branch:** `agent/leonidas/t-20261013-7eff`
**Route censused:** shipping `tools/reader_lex.py` = `baseline.py` floor +
`tools/lex_projection.fix_line` (R1–R5 + S25), on the canonical seed-1 hard
suite (`dir_hash b2c460d2fb5a…`, regenerated and hash-verified this session).
**Headline:** floor 12/100 → shipping 23/100 → **77 misses: 63 segmentation,
9 matching-case, 5 matching-glyph.** Lex helped 17 of the 77 partially,
hurt 0, neutral 60 — and broke 0 of the 12 floor-exact reads while fixing 11.

## Decision tree (primary root cause, per miss)

```
77 hard misses
├─ final.lower() == label.lower() ............  9  matching-case
│    (every character recovered; only case decisions wrong)
├─ len(final) != len(label) ................... 63  segmentation
│    (fewer/more characters: fused, split, dropped or invented
│     glyphs — the S22 segmentation signature)
└─ same length, substitutions ................  5  matching-glyph
```

Invest in that order of size: **the segmentation/mask lane owns 82% of
the residue.** Six near-zero families — collage 0/8, corrosion 0/8,
cross-shadow 0/8, darts 0/8, strippy 0/8, spiderweb 1/9 — contribute
48 of the 77 misses (47 of them segmentation-primary). That is the
image-side wall S25/S27/S30 already identified; this census confirms
it item-by-item on the settled 23/100 route and shows no text-side
lane (lex, case, count arbitration) can close more than a fraction
of it. The case lane (9, four of them stitch) is reader-side case
logic (`_case_of` twins), *not* lex re-casing, which S22 records as
already rejected. Glyph substitution (5) is a residue, not a lane.

## How this was measured (receipt-based, reproducible)

No new bench run. Two committed artifacts, recomputed:

1. **Raw floor reads** — `reports/post27-screens/20261012T170353Z-easy-hard.json`
   (reader `python3 baseline.py {image}`, canonical seed-1, 100 hard items).
2. **Reader structure** — `reports/s25-piece-gap/hard-reads.jsonl`
   (Cormac's S25 replication of baseline's mask path: reader word count
   and glyph pieces per word, same suite).
3. **Final shipping read** = `fix_line(floor_got)` with current
   `tools/lex_projection.py`, recomputed per item.

**Validation (script-enforced):** floor exact must be 12, recomputed
shipping exact must be 23, misses 77 — `tools/s43_failure_census.py`
exits non-zero otherwise. It also asserts label/family agreement
between the two artifacts on all 100 items. The recomputation differs
from Cormac's collected pre-S25 reads on exactly 4 items, all explained
by the S25 wiring itself (stitch-0005 and snow-0008 become exact;
stitch-0007 digit-joined; dark-on-dark-0000 orphan-dropped).

**Spot check (live, this session):** after regenerating the suites
(hash `b2c460d2fb5a` matched), `tools/reader_lex.py` on
spiderweb-0000, split-0003, snow-0003, stitch-0007 and corrosion-0000
reproduced the derived final reads exactly, and the S25
`route_pieces` replication reproduced the committed glyph-piece
counts on the same five. 5/5.

### Definitions (proxies, named as such)

- **Segmentation (primary):** final read has fewer/more characters
  than the label. Supporting reader-stage diagnostics are reported
  per item: `seg_word` FAIL if the reader's word count ≠ label token
  count (50/77 FAIL), `seg_piece` FAIL if native `R.segment` piece
  counts ≠ label token lengths (72/77 FAIL). The native piece count
  is *evidence, not proof*: pieces pass through `split_wide` rescue
  before matching, and 7 of the 14 matching-primary misses carry a
  native piece FAIL whose characters were nevertheless recovered.
- **Matching:** only claimed isolable when the character structure
  survives — case-only (all characters, wrong case) or same-length
  substitutions. Under segmentation-primary misses it is marked
  `not-isolable`, except `glyphs-recovered` where only tokenisation
  is wrong. Per-task question answered this way deliberately:
  asserting a matching verdict under a collapsed mask would be
  inventing evidence.
- **Lex effect (token-aware):** helped if exact-token matches vs the
  label increased floor→final, or held while char Levenshtein
  distance fell; hurt is the mirror; neutral otherwise. (A char-only
  metric mislabels split-0001 as hurt — lex recovered the exact token
  `MEriDIAn` there; the token-aware rule classifies it as helped.)

### Limitations

Single seed (seed-1 canonical), one route (shipping lex), stage
attribution from structural receipts rather than per-item visual
inspection, and lex effect measured on text distance/token overlap —
it cannot see *why* a projection fired. Cross-seed stability is
S38's question (Achilles: seed-2 74/29), not claimed here.

## Results by family

| family | exact | misses | segmentation | matching-case | matching-glyph |
|---|---:|---:|---:|---:|---:|
| collage | 0/8 | 8 | 8 | 0 | 0 |
| corrosion | 0/8 | 8 | 8 | 0 | 0 |
| cross-shadow | 0/8 | 8 | 8 | 0 | 0 |
| cut | 5/8 | 3 | 2 | 1 | 0 |
| dark-on-dark | 3/8 | 5 | 3 | 1 | 1 |
| darts | 0/8 | 8 | 8 | 0 | 0 |
| obstruction | 4/8 | 4 | 3 | 1 | 0 |
| snow | 5/9 | 4 | 2 | 1 | 1 |
| spiderweb | 1/9 | 8 | 8 | 0 | 0 |
| split | 3/9 | 6 | 4 | 1 | 1 |
| stitch | 2/9 | 7 | 2 | 4 | 1 |
| strippy | 0/8 | 8 | 7 | 0 | 1 |

## Lex effect on the 77 misses

| effect | count | reading |
|---|---:|---|
| helped (partial) | 17 | closer to the label, still a miss — lex is doing real work even inside the residue |
| neutral | 60 | final == floor or no distance/token gain; mostly collapsed masks lex cannot reconstruct |
| hurt | 0 | lex broke none of the 77; on all 100 it fixed 11 floor misses and broke 0 floor-exact reads |

## Reproduce

```bash
python3 tools/make_suites.py                       # hash must print b2c460d2fb5a
python3 tools/s43_failure_census.py                 # summary + VALIDATION: PASS
python3 tools/s43_failure_census.py --table         # the appendix below
python3 tools/s43_failure_census.py --json reports/s43_failure_analysis.json
```

## Appendix — all 77 misses

| id | family | primary | seg word/piece | matching | lex (dist floor→final) | final read vs label |
|---|---|---|---|---|---|---|
| collage-0000 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (25→25) | `2HDEQRIkBI` ≠ `Pebble rivet rosette sAil` |
| collage-0001 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (20→20) | `zIHTwBizQM` ≠ `marble keel 37 Drift` |
| collage-0002 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (14→14) | `EHQiTIHN` ≠ `lupine 43 talon` |
| collage-0003 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (24→24) | `iBMQQIHFIn` ≠ `tUNDra FELDSPAR Delta wren` |
| collage-0004 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (21→21) | `IZZEEH44TgzP` ≠ `cobalt ZePhyr 34 valley` |
| collage-0005 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (23→23) | `HHQwmwvEFa` ≠ `parchment Saffron lantern` |
| collage-0006 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (19→19) | `?` ≠ `Beacon Nimbus QUILL` |
| collage-0007 | collage | segmentation | FAIL/FAIL | not-isolable | neutral (19→19) | `1ETkWjziaL` ≠ `forge 53 ZENITH nectar` |
| corrosion-0000 | corrosion | segmentation | FAIL/FAIL | not-isolable | neutral (14→14) | `4714fjW lMJJS w` ≠ `GROVE ember` |
| corrosion-0001 | corrosion | segmentation | OK/FAIL | not-isolable | neutral (13→13) | `ii1file ZKiLifiii` ≠ `forge Zenith` |
| corrosion-0002 | corrosion | segmentation | FAIL/FAIL | not-isolable | neutral (20→20) | `uObLLIIAIi keeL 099 i 1 fiVal r` ≠ `OBSIDIAN keel 003 clover` |
| corrosion-0003 | corrosion | segmentation | FAIL/FAIL | not-isolable | neutral (17→17) | `ma rh l C ZIdalg NEHiRA 1 ifCbO` ≠ `marble ZIGZag NEBULA ivory` |
| corrosion-0004 | corrosion | segmentation | FAIL/FAIL | not-isolable | helped (16→14) | `TlmluTi wdl low 07 slGw4it Fennel SASf` ≠ `qUArTz willow 07 summit Fennel SAGE` |
| corrosion-0005 | corrosion | segmentation | FAIL/FAIL | not-isolable | neutral (10→10) | `I0x4ch kIaH ilw 06` ≠ `larch Marble 06` |
| corrosion-0006 | corrosion | segmentation | FAIL/FAIL | not-isolable | neutral (22→22) | `lUACJaENT aeRR ch1 SC l kAi LEie lifUJn` ≠ `PARCHMENT EMBER chisel VALLEY linen` |
| corrosion-0007 | corrosion | segmentation | FAIL/FAIL | not-isolable | neutral (9→9) | `s2l8 t e xaLl` ≠ `sable keel` |
| cross-shadow-0000 | cross-shadow | segmentation | FAIL/FAIL | not-isolable | neutral (30→30) | `?foeot qofd` ≠ `bRAsS RIDGE MisTrAl parchment fjord` |
| cross-shadow-0001 | cross-shadow | segmentation | OK/FAIL | not-isolable | neutral (6→6) | `wd? tarn` ≠ `breeze tarn` |
| cross-shadow-0002 | cross-shadow | segmentation | FAIL/FAIL | not-isolable | neutral (15→15) | `? 008 q3a13nw` ≠ `Fjord surf 008 Sparrow` |
| cross-shadow-0003 | cross-shadow | segmentation | OK/FAIL | not-isolable | neutral (8→8) | `? sEQuoIA sLATE island` ≠ `bolt SEQUOIA SLATE island` |
| cross-shadow-0004 | cross-shadow | segmentation | FAIL/FAIL | not-isolable | helped (9→7) | `nebula 006 cObALT` ≠ `Basil nebula 006 cObAlT` |
| cross-shadow-0005 | cross-shadow | segmentation | FAIL/FAIL | not-isolable | neutral (12→12) | `? harbor marble salmon` ≠ `quill LUpinE harbor marble salmon` |
| cross-shadow-0006 | cross-shadow | segmentation | FAIL/FAIL | not-isolable | neutral (7→7) | `?ron 84 Spring` ≠ `mesa heron 84 Spring` |
| cross-shadow-0007 | cross-shadow | segmentation | FAIL/FAIL | not-isolable | neutral (19→19) | `P?iR SPaRrOW` ≠ `Penguin 0 trail swift SPaRrOW` |
| cut-0001 | cut | matching-case | OK/OK | case-only | neutral (1→1) | `Sage ember indigo falcon` ≠ `Sage ember Indigo falcon` |
| cut-0002 | cut | segmentation | FAIL/FAIL | not-isolable | helped (7→6) | `TrAiL fennel Fl lhlT` ≠ `TrAIL fennel FLINT` |
| cut-0004 | cut | segmentation | OK/FAIL | not-isolable | neutral (5→5) | `HEA77JFR sParrow Clover` ≠ `HEATHER sparrow Clover` |
| dark-on-dark-0000 | dark-on-dark | matching-glyph | FAIL/FAIL | glyph-substitution | helped (12→9) | `Vi ULL NECTAR raVen nnA` ≠ `VIOLET NECTAR raven 006` |
| dark-on-dark-0002 | dark-on-dark | segmentation | OK/FAIL | not-isolable | helped (4→2) | `stalactite obsidian QUArtz 000 jaspl` ≠ `stalactite obsidian QUArtz 000 jasper` |
| dark-on-dark-0005 | dark-on-dark | segmentation | OK/FAIL | not-isolable | neutral (2→2) | `meteor gord vapoR` ≠ `meteor fjord vapoR` |
| dark-on-dark-0006 | dark-on-dark | segmentation | FAIL/FAIL | not-isolable | helped (4→3) | `db l ta LANTERn 02 nECtar` ≠ `delta LANTERn 02 nECtar` |
| dark-on-dark-0007 | dark-on-dark | matching-case | OK/FAIL | case-only | helped (3→1) | `THICKET summit slate spring bRASs` ≠ `THICKET summit slate spring brASs` |
| darts-0000 | darts | segmentation | FAIL/FAIL | not-isolable | neutral (14→14) | `? HaHJH R?en ?Ed L?cH` ≠ `Harbor Raven WREN LARCH` |
| darts-0001 | darts | segmentation | FAIL/FAIL | not-isolable | neutral (14→14) | `ji A ? ?R??????` ≠ `ORCHID fAlCOn` |
| darts-0002 | darts | segmentation | FAIL/FAIL | not-isolable | neutral (29→29) | `?b??l?? ?` ≠ `harbor vertex marble sable drift` |
| darts-0003 | darts | segmentation | OK/FAIL | not-isolable | neutral (14→14) | `? ?McJjb?jJvT K` ≠ `carbon flint 5` |
| darts-0004 | darts | segmentation | FAIL/FAIL | not-isolable | neutral (34→34) | `???6t?iP ?` ≠ `Timber Violet crystal meridian vElLum` |
| darts-0005 | darts | segmentation | FAIL/FAIL | not-isolable | neutral (30→30) | `??????udx A` ≠ `raVen zenith coral ANCHOR torque` |
| darts-0006 | darts | segmentation | FAIL/FAIL | not-isolable | neutral (23→23) | `??q?? b?xT` ≠ `mesa Ivory basil MEridIan` |
| darts-0007 | darts | segmentation | FAIL/FAIL | not-isolable | neutral (19→19) | `jc ?v yo?? ??jJ??? ?` ≠ `oasis SuMMIT crest` |
| obstruction-0001 | obstruction | segmentation | OK/OK | not-isolable | neutral (8→8) | `?jlIRT plumQfQpp` ≠ `FlINT plume` |
| obstruction-0002 | obstruction | segmentation | OK/FAIL | not-isolable | helped (6→5) | `torque 04 BraIY` ≠ `Torque 04 Bramble` |
| obstruction-0003 | obstruction | matching-case | OK/OK | case-only | neutral (1→1) | `Moss Fjord` ≠ `MOss Fjord` |
| obstruction-0007 | obstruction | segmentation | FAIL/FAIL | not-isolable | neutral (21→21) | `FliNT cARBoN dHR Gad?jDsPAR` ≠ `Flint CARBON drift Garnet 000 FELDSPAR` |
| snow-0000 | snow | segmentation | FAIL/FAIL | not-isolable | neutral (3→3) | `SAIL tarn CarL Jn` ≠ `SAIL tarn Carbon` |
| snow-0001 | snow | matching-case | OK/OK | case-only | neutral (2→2) | `beacon IsLAND jAspEr PLuME` ≠ `beacon ISLAND jAspEr PLUME` |
| snow-0003 | snow | matching-glyph | OK/OK | glyph-substitution | neutral (2→2) | `HEATHER rert` ≠ `HEATHER reef` |
| snow-0004 | snow | segmentation | OK/FAIL | not-isolable | neutral (2→2) | `DrIR 60 iSlaNd LEDGe Grove` ≠ `DrIft 60 iSlaNd LEDGe Grove` |
| spiderweb-0000 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (11→11) | `?I4` ≠ `Flint tIMBEr` |
| spiderweb-0001 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (14→14) | `?` ≠ `HOrIZoN zephyr` |
| spiderweb-0002 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (18→18) | `M?` ≠ `Moss PRAIRIE Nebula` |
| spiderweb-0003 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (27→27) | `?LJj?` ≠ `HARBOR crane Heather lUpiNe` |
| spiderweb-0004 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (25→25) | `?GJL` ≠ `talon Fossil timber Cedar` |
| spiderweb-0005 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (13→13) | `?w` ≠ `juniper Hollow` |
| spiderweb-0006 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (32→32) | `?ij?AcJTJT` ≠ `tundra duNE cIpHEr Willow STALACTITE` |
| spiderweb-0007 | spiderweb | segmentation | FAIL/FAIL | not-isolable | neutral (31→31) | `?` ≠ `signal INDIGO osprey 004 Cipher` |
| split-0000 | split | segmentation | OK/FAIL | not-isolable | neutral (2→2) | `hollow MARBLE 07 IJMBER` ≠ `hollow MARBLE 07 UMBER` |
| split-0001 | split | segmentation | FAIL/FAIL | not-isolable | helped (3→4) | `comet hE MEriDIAn` ≠ `Comet MEriDIAn` |
| split-0003 | split | matching-case | OK/FAIL | case-only | helped (2→1) | `Umber cIPHER fossil scarp marble` ≠ `Umber CIPHER fossil scarp marble` |
| split-0004 | split | segmentation | OK/FAIL | not-isolable | neutral (5→5) | `VIolet 001 egTshER` ≠ `Violet 001 embER` |
| split-0005 | split | segmentation | OK/FAIL | not-isolable | helped (4→2) | `mistral 6 lpaz lantern` ≠ `mistral 6 Topaz lantern` |
| split-0006 | split | matching-glyph | OK/FAIL | glyph-substitution | neutral (2→2) | `brass tide canyon cafmon nebULA` ≠ `brass tide canyon carBon nebULA` |
| stitch-0000 | stitch | segmentation | FAIL/FAIL | not-isolable | neutral (4→4) | `Canyon 53 toIla lz heron basil` ≠ `Canyon 53 topaz heron basil` |
| stitch-0001 | stitch | matching-glyph | OK/FAIL | glyph-substitution | neutral (3→3) | `njMDRA harbor` ≠ `TUNDRA harbor` |
| stitch-0003 | stitch | matching-case | OK/FAIL | case-only | helped (2→1) | `oRChid Meteor` ≠ `ORChid Meteor` |
| stitch-0004 | stitch | matching-case | FAIL/FAIL | case-only | helped (8→1) | `ivorY paRcHMEnt summit` ≠ `ivory paRcHMEnt summit` |
| stitch-0006 | stitch | segmentation | FAIL/FAIL | not-isolable | neutral (3→3) | `lra Ven horizon` ≠ `raven horizon` |
| stitch-0007 | stitch | matching-case | FAIL/FAIL | case-only | helped (3→1) | `CoPPER 008 linen` ≠ `COPPER 008 linen` |
| stitch-0008 | stitch | matching-case | OK/FAIL | case-only | helped (4→2) | `haRBor LagOon Wren lagoOn` ≠ `haRBor LagOon wren lagOOn` |
| strippy-0000 | strippy | segmentation | OK/FAIL | not-isolable | helped (10→8) | `1LJUU11 mesa valley` ≠ `FOSSIL Mesa valley` |
| strippy-0001 | strippy | segmentation | FAIL/FAIL | not-isolable | neutral (38→38) | `iwsaz w zvwvwr lmzzlvwzzz xazmizivw izsaziasazz` ≠ `ivory reef lantern prairie horizon` |
| strippy-0002 | strippy | segmentation | FAIL/FAIL | not-isolable | neutral (29→29) | `ZmuuN iuuuumwuui aiEiUmw aiVqZVVZ` ≠ `Parchment Ridge ROSETTE` |
| strippy-0003 | strippy | segmentation | FAIL/FAIL | not-isolable | neutral (20→20) | `rnuT s GiJ GGq Gi ZrTrZ` ≠ `falcON 005 GLACIER` |
| strippy-0004 | strippy | segmentation | OK/FAIL | not-isolable | neutral (17→17) | `liulJAllts ltsiuiml` ≠ `lUpIne Cedar` |
| strippy-0005 | strippy | matching-glyph | OK/FAIL | glyph-substitution | neutral (11→11) | `zztlz 1 rIJJz tiiz` ≠ `sable 1 Forge tide` |
| strippy-0006 | strippy | segmentation | FAIL/FAIL | not-isolable | neutral (36→36) | `za JzzTmJ rwwzxZzzzx rZZZnZ JfZwwxJzzzoz` ≠ `violet Canyon CARBON Meadow` |
| strippy-0007 | strippy | segmentation | OK/FAIL | not-isolable | helped (13→11) | `gLacier TnicrcT EtiKT` ≠ `glacier thicket suRf` |
