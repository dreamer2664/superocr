# t-407f first measurement — split / stitch / strippy / cut repairs

Structural toolkit: undo_split (cut+dy search, row-profile correlation),
undo_stitch (seam-colour detection + per-strip roll), strippy loose cut
(a<=220 recovers stripe-attenuated ink; paper never below 225) + closing,
cut vertical closing (bridges 3-5px slashes). Then the shared classic chain.

| family | seed | n | exact | char |
|---|---|---|---|---|
| split | 1 | 30 | 0.00 | 0.51 |
| split | 7 | 30 | 0.03 | 0.48 |
| split | 13 | 30 | 0.03 | 0.45 |
| stitch | 1 | 30 | 0.00 | 0.45 |
| stitch | 7 | 30 | 0.03 | 0.49 |
| stitch | 13 | 30 | 0.00 | 0.42 |
| strippy | 1 | 30 | 0.00 | 0.26 |
| strippy | 7 | 30 | 0.00 | 0.36 |
| strippy | 13 | 30 | 0.03 | 0.35 |
| cut | 1 | 30 | 0.03 | 0.31 |
| cut | 7 | 30 | 0.03 | 0.31 |
| cut | 13 | 30 | 0.00 | 0.30 |

## failures (seed 1, first four per family)

- `split[0]` expected `hollow MARBLE 07 UMBER` got `hol low AMRBLE 02 LpmER`
- `split[1]` expected `Comet MEriDIAn` got `comet MF FtpIAo`
- `split[2]` expected `canyon SCARP ZeniTh 00 brook` got `canYon SCARp zenith 00 bRook`
- `split[3]` expected `Umber CIPHER fossil scarp marble` got `UlwbeF cjPHEk Mssil scaFL lwaFble`
- `stitch[0]` expected `Canyon 53 topaz heron basil` got `CaDYoD 53 toFka 2 heFoD basil`
- `stitch[1]` expected `TUNDRA harbor` got `THNDRd 0aEQoE`
- `stitch[2]` expected `chIsel surf 20 Rosette` got `chIsel suRf 20 Rosette`
- `stitch[3]` expected `ORChid Meteor` got `Orchid Meteor`
- `strippy[0]` expected `FOSSIL Mesa valley` got `PONNJL M98A vAH9Y`
- `strippy[1]` expected `ivory reef lantern prairie horizon` got `JvoFy F99f l9nt9Fn pF9JFJ9 hoFJRon`
- `strippy[2]` expected `Parchment Ridge ROSETTE` got `p9rchjw9nt RjdQ9 RO8RTTR`
- `strippy[3]` expected `falcON 005 GLACIER` got `falcon 885 GLACIER`
- `cut[0]` expected `zigzag 005 meadow vellum` got `RigR9g 995 mEadow vwllHm`
- `cut[1]` expected `Sage ember Indigo falcon` got `59Q4 9rTb9r lmdIQo f9Icom`
- `cut[2]` expected `TrAIL fennel FLINT` got `RAjL fAHnAl PLjNT`
- `cut[3]` expected `pebble 2 CANYON` got `p0bbl0 2 CANYON`

## verdict

The repairs work: split/stitch realign to one text band (structure tests
green), strippy recovers its hidden rows, cut bridges its slashes. Char
accuracy is then capped by the same glyph matcher as t-2ca7 - the S1/S2
matcher is the collective bottleneck, not the structure. True numbers
above; nothing rounded, gallery committed (honesty rule, JOBS.md).
