# t-2ca7 first measurement — obstruction & dark-on-dark readers

Classic pipeline (no ML): high-pass residual + sigma/p99 threshold,
despeck, column segmentation, split_wide, DejaVu template matching,
case-twin height rule, lexicon rerank. Measured on generator data.

| family | seed | n | exact | char |
|---|---|---|---|---|
| obstruction | 1 | 30 | 0.03 | 0.44 |
| obstruction | 7 | 30 | 0.00 | 0.44 |
| obstruction | 13 | 30 | 0.07 | 0.53 |
| dark-on-dark | 1 | 30 | 0.10 | 0.59 |
| dark-on-dark | 7 | 30 | 0.03 | 0.65 |
| dark-on-dark | 13 | 30 | 0.03 | 0.59 |

## failures (seed 1, first six per family)

- `obstruction[1]` expected `FlINT plume` got `C d3 FlINT plHml W A J`
- `obstruction[2]` expected `Torque 04 Bramble` got `mFque 04 BFajBble`
- `obstruction[3]` expected `MOss Fjord` got `SMoss fjoRd`
- `obstruction[4]` expected `Violet 3 stalactite` got `violet 3 stalactite`
- `obstruction[5]` expected `Crane 005 spring` got `CFaHe 005 spFlng`
- `obstruction[6]` expected `BRAMbLE meridian Umber mistral` got `BRAMbLE meFjdjaD MDbeF mjstFal`
- `dark-on-dark[0]` expected `VIOLET NECTAR raven 006` got `UTOLET NEC7MR FaVeD 006`
- `dark-on-dark[1]` expected `walrus BrooK cOmeT Penguin Hazel` got `JNHIFHs HFooK cOJnoT PoHgHiH HHzoI`
- `dark-on-dark[2]` expected `stalactite obsidian QUArtz 000 jasper` got `alactito obsidiaN quaRtz 000 jasD`
- `dark-on-dark[3]` expected `Slate Zenith violet 70` got `SIato ZoHith vioIot 70`
- `dark-on-dark[4]` expected `Osprey vApor Carbon DELTA` got `OspFeV vapoR CaFboD DEL7M`
- `dark-on-dark[5]` expected `meteor fjord vapoR` got `lweteor DoFd vapoR`

## what works / what remains

- dark-on-dark: vignette removed by high-pass; case-twins fixed by
  within-word height rule; residual confusion is glyph-shape matching
  (S1 template work / S2 CNN).
- obstruction: smudge edges (mid-strength residuals) suppressed by the
  p99-anchored threshold; remaining errors are eroded strokes at the
  smudge/ink overlap — needs confidence+fallback (S2) or better matcher.

The bar (95/100) is NOT claimed here. These are true first numbers;
the failure gallery stays in the repo (honesty rule, JOBS.md).
