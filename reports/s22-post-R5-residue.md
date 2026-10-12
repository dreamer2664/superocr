# S22 — the post-R5 residue map (t-20261012-dc2e)

**What this is.** After the ladder (#27, floor 54/12), the lex projection (#47, R1-R4)
and R5 (#49) landed, the shipping reader is `tools/reader_lex.py` = floor + lex. This is
the classified map of **everything still wrong** on the official suites, so the next wave
can target by class instead of by anecdote. Receipt-based and reproducible: no new claims,
the numbers below are the merged code applied to raw floor rows.

**Route measured.** `floor rows -> tools/lex_projection.fix_line` — exactly what
`reader_lex.py` runs (wrapper = floor output + fix_line). Raw floor rows:
`main-v2-s1.json` / `main-v2-s2.json` (my runs; seed-1 set verified **200/200
item-identical** to the committed floor receipt `reports/post27-screens/20261012T170353Z`;
seed-2 set under the pre-R5 lex reproduces the committed wrapper receipt `69/24` exactly —
and the +5/+5 below is R5's own gain there, not this task's). Lex file:
`tools/lex_projection.py` @ `b2f3004` (sha `79eb223e88e9`, R5 present).

## Totals after R5 (both official suites)

| suite | seed | exact | case-only | fewer-chars | more-chars | subs(n) | misses |
|---|---:|---:|---:|---:|---:|---:|---:|
| easy | 1 | **73** | 12 | 6 | 6 | 3 | 27 |
| easy | 2 | **74** | 14 | 5 | 4 | 3 | 26 |
| hard | 1 | **21** | 8 | 35 | 32 | 4 | 79 |
| hard | 2 | **29** | 8 | 35 | 22 | 6 | 71 |

*(`fewer`/`more` = fewer/more characters than the label — the segmentation signature:
fused pieces, dropped pieces, split pieces. `subs(n)` = same length, n differing
positions.)*

Pooled over the 200 reads per suite:

- **easy 147/200** (73.5 avg). The 53 misses are **~half case-only (26), 40% segmentation
  (21), 11% substitutions (6)**.
- **hard 50/200** (25 avg). The 150 misses are **83% segmentation (124), 11% case (16),
  7% subs (10)** — hard is a segmentation wall, full stop.

## What this says — three lanes, in order of size

1. **Segmentation owns hard** (124/150 hard misses, 21/53 easy misses). This is where
   the walls live (collage/corrosion/strippy/stripper-family reads produce whole-string
   garbage; the `strippy` misses below are representative). R5's joins shaved the easy
   side of it; the residue is full-piece fusion/splitting, i.e. the S8-lever-C/`split_wide`
   family plus the wall families. Corrosion remains 0/8 under every route measured today.
2. **Case-only is the biggest easy class (26) — and it is lex-immune BY DESIGN.** R1
   never re-cases a clean token ("case patterns are the reader's job"). Every one of the
   12-14 case misses is a reader-side case decision (`pINNaCLe`, `WREn`, `WALRUS taRn`...).
   Note for the record: lex-side re-casing and the image-cap case-rule were **already
   rejected** as levers earlier today — this class must be won in the reader's case logic
   (the wave-2..5 family), not in the post-pass.
3. **Substitutions are nearly gone** (6 easy, 10 hard): the matcher's top-8 already
   contains the right glyph for most of these; the residue is case/twin-adjacent or
   hard-family damage. Not a separate lane.

For reference, the bar gaps this map implies (pooled small-n caveats aside):
easy 73.5 -> 98 = **~25 items to find**; hard 25 -> 95 = **~70 items**. The map says where
they can plausibly come from: ~half of easy's gap is case-lane work; the other ~half plus
almost all of hard's gap is segmentation, with corrosion (16 reads, 0 correct) sitting
inside the hard number as its own unresolved wall.

## Reproduce (two commands)

```
python3 tools/s22_residue.py --lex main-v2-s1.json     # prints tables + full miss lists
python3 tools/s22_residue.py reports/post27-screens/20261012T170353Z-easy-hard.json  # pre-lex cross-check
```

Raw floor rows for both seeds are the `got/label` pairs of the committed receipts
(`reports/post27-screens/20261012T170353Z` for seed 1; the seed-2 wrapper receipt on main
for the seed-2 labels) — the script takes either shape, with `--lex` to apply the merged
post-pass.


## Appendix — the easy miss lists (post-R5, both seeds)

Seed 1 (from `main-v2-s1.json`, 27 misses):

```
easy: 73/100 exact | {'exact': 73, 'case-only': 12, 'fewer-chars': 6, 'more-chars': 6, 'subs(2)': 1, 'subs(4)': 1, 'subs(5)': 1}
      easy-0000          [case-only  ] 'pINNaCLe heather' != 'PINNaCLe heather'
      easy-0001          [subs(2)    ] 'Falcon BilTh' != 'Falcon Birch'
      easy-0002          [fewer-chars] 'Harbor FalcoN EMBER HArBoR HORD' != 'Harbor FalcoN EMBER HArBoR FJORD'
      easy-0003          [fewer-chars] 'DriO Keel' != 'Drift Keel'
      easy-0006          [more-chars ] 'eIIRF 7 anchor' != 'sURF 7 anchor'
      easy-0011          [case-only  ] 'WREn quARtZ' != 'WrEn quARtZ'
      easy-0014          [subs(4)    ] 'OASIS breeze 73 FFNmPI' != 'OASIS breeze 73 FENNEL'
      easy-0019          [case-only  ] 'RIVET SLATE tarn WALRUS taRn' != 'RIVET SLATE tarn WaLRUS taRn'
      easy-0023          [more-chars ] 'lvleSa SPARROW nT' != 'Mesa SPARROW 07'
      easy-0026          [case-only  ] 'cedar thistle willow 85 umber wALRUS' != 'cedar thistle willow 85 umber wAlRUS'
      easy-0027          [more-chars ] 'delta Rivet 00 TARn NI' != 'delta Rivet 00 TARN'
      easy-0032          [case-only  ] 'Rosette BRook fJOrD cinder CIPHER' != 'Rosette BRook fJOrD cinder CIPHEr'
      easy-0033          [case-only  ] 'Garnet 007 oasis violet SUndiaL ShALe' != 'Garnet 007 oasis violet SUndIaL ShALe'
      easy-0036          [fewer-chars] 'uINT CoRal glacier Indigo pinnacle' != 'FLINT CoRal glacier Indigo pinnacle'
      easy-0041          [more-chars ] 'falcon Th131' != 'falcon Tarn'
      easy-0042          [more-chars ] 'brook parchment Ivo fT umBEr zephyr' != 'Brook parchment Ivory umBEr zephyr'
      easy-0048          [case-only  ] 'brass crane stalactite jasPEr NecTAr' != 'brass crane stalactite jaSPEr NecTAr'
      easy-0057          [fewer-chars] 'Wolet talon 29 BASiL parchment' != 'Violet Talon 29 BASiL parchment'
      easy-0060          [case-only  ] 'spring Sage SequOiA sTALACtItE' != 'spring Sage SequOIA sTALACtItE'
      easy-0065          [fewer-chars] 'saMron nectar trail 3' != 'saffron nectar trail 3'
      easy-0068          [subs(5)    ] 'D1rch cRYStAL gq' != 'birch cRYStAl 79'
      easy-0072          [more-chars ] 'DUNE zephyr StA lACTUTT' != 'DUNE zephyr StAlACTITE'
      easy-0074          [case-only  ] 'shale larCh saffron' != 'shale larCH saffron'
      easy-0080          [case-only  ] 'breEze heather indigo zenith EMBER' != 'breEze heather Indigo zenith EMBER'
      easy-0084          [case-only  ] 'GLaCieR BRASS CindeR penguin feldspar' != 'GlaCieR BRASS CindeR penguin feldspar'
      easy-0086          [fewer-chars] 'IVORY cjTSMl SPRING marble 0' != 'IVORY cryStAl SPRING marble 0'
      easy-0091          [case-only  ] 'raven raVen' != 'raven raven'
```

Seed 2 (from `main-v2-s2.json`, 26 misses):

```
easy: 74/100 exact | {'exact': 74, 'case-only': 14, 'fewer-chars': 5, 'more-chars': 4, 'subs(4)': 1, 'subs(1)': 1, 'subs(8)': 1}
      easy-0010          [fewer-chars] 'Drey moss flint osprey swift' != 'osprey moss flint osprey swift 79'
      easy-0011          [fewer-chars] 'Bte copPer 7 basil misTRAl Sha' != 'slate copPer 7 basil misTRAl Shale'
      easy-0013          [more-chars ] 'Garnet scaJTl OrChId Torque 26 meteor' != 'Garnet scarp OrChId Torque 26 meteor'
      easy-0016          [fewer-chars] 'marble JAsPER PINNAcLE Drift FaLcoN 0l' != 'Marble JASPER PINNACLE Drift FaLCoN 008'
      easy-0018          [more-chars ] 'LlJHALI FALCON 7Q sllMrlnlP' != 'COBALT FALCON 29 suMmIt'
      easy-0022          [case-only  ] 'island 5 HoRIzoN suNDiaL jasper Rosette' != 'island 5 HORIZON suNDiaL jasper Rosette'
      easy-0038          [case-only  ] 'Vapor raven ancHor' != 'VapOr raven ancHor'
      easy-0046          [case-only  ] 'tarn summit KEeL cinder violet' != 'tarn summit KeeL cinder violet'
      easy-0052          [case-only  ] 'canyon Umber 64 RIvET fjord' != 'canyon Umber 64 RIVET fjord'
      easy-0053          [case-only  ] 'prairie ZENitH island 08' != 'prairie ZENitH Island 08'
      easy-0054          [case-only  ] 'RIDGE CLOvER 07 vertex Sail cinder' != 'RIDGE ClOvER 07 vertex Sail cinder'
      easy-0057          [subs(4)    ] 'moss meadow 51XLACT1TE SIGNAL 5 lupine' != 'moss meadow STALACTITE SIGNAL 5 lupine'
      easy-0066          [case-only  ] 'brAMbLE Canyon' != 'brAMblE Canyon'
      easy-0067          [case-only  ] 'cipher SparroW amber PraiRie salmon' != 'cipher SparRoW amber PraiRie salmon'
      easy-0076          [case-only  ] 'IVORY 006 parchment torque chiSeL Delta' != 'IVORY 006 parchment Torque chISeL Delta'
      easy-0079          [case-only  ] 'osprey oasis COMET' != 'Osprey oasis COMET'
      easy-0082          [case-only  ] 'BRAMBLE FLiNT TARN MESA Sparrow 41' != 'BRAMBLE FliNT TARN MESA Sparrow 41'
      easy-0085          [case-only  ] 'BEACON talon rosette OSPREY Spring 01' != 'BEACON Talon rosette OSPREY Spring 01'
      easy-0088          [more-chars ] 'FAJ CON lantern' != 'FALCON lantern'
      easy-0089          [subs(1)    ] 'COBAL nectar lantern talon Sequoia' != 'CORAL nectar lantern talon Sequoia'
      easy-0090          [fewer-chars] 'llow Obsidian otter Walrus falcon' != 'willow Obsidian otter Walrus falcon'
      easy-0092          [more-chars ] 'PARCHMENT fa l con saIL TmbER' != 'PARCHMENT falcon saIL TimbER'
      easy-0095          [case-only  ] 'wharf 09 cinder violet' != 'Wharf 09 cinder violet'
      easy-0097          [subs(8)    ] 'HOLLOW BRAMBLE 007 MFAnnW' != 'Hollow BRAMBLE 007 MEADOW'
      easy-0098          [fewer-chars] 'ASTT NIFADOW tundra va11e' != 'BASIL MEADOW tundra valley'
      easy-0099          [case-only  ] 'osprey jAspER thistle north Thistle' != 'osprey jASpER thistle north Thistle'
```

*Provenance: my rows (in-process `baseline.read_text`, seed 1/2, suites `b2c460d2fb5a` /
`ec64cd63790d`); lex at `79eb223e88e9`; seed-1 floor rows item-verified against the
committed receipt; seed-2 control verified against the committed wrapper totals. Full
miss lists print from the script; easy lists are also in the PR description.*
