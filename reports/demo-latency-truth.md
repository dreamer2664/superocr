# Demo latency — the honest number (S18, t-20261012-777f, pericles)

**What was wrong.** `tools/demo_latency.py` POSTed the *same generated image*
`--repeats` times, so repeats 2..7 rode warm caches. On one easy image:
531 ms cold, then 18 ms × 6 — median 19.8 ms. The headline described the
cache, not the product. (The caches themselves are a measured win — barry's
perf-recipe — but a demo number must describe a **first read**.)

**The fix.** One distinct image per repeat: seed = pinned base + 1000·i
(seeds stay pinned, so the run is still reproducible from a clean clone).
Nothing else touched; the JSON is tagged with the measurement method.

**The honest numbers** (current main `891e44e` + this fix; 7 distinct images
per family; server-side = inside the shared recognise() call):

| probe | median end-to-end | median server |
|---|---:|---:|
| easy | 344 ms | 341 ms |
| snow | 298 ms | 294 ms |
| obstruction | 452 ms | 449 ms |
| split | 312 ms | 309 ms |
| strippy | 861 ms | 858 ms |
| dark-on-dark | 531 ms | 528 ms |
| **overall (auto probes)** | **406 ms** | — |

**Bar check.** Every auto probe ≤ 10 s: **MET**, with ~12× headroom on the
worst family (strippy, 861 ms). Warm-cache repeats of an identical image land
at 4–20 ms — kept as a note, not as the headline.

Raw per-request numbers: `reports/demo-latency.json`.
