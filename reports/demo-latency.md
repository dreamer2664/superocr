# S4 browser demo — measured latency report (t-20261011-27bc)

All numbers from `python3 tools/demo_latency.py --repeats 7` on the
merged reader (per-request values in `demo-latency.json` beside this
file; seeds pinned in the script, reproducible from a clean clone).
Server-side ms ≈ end-to-end ms (same box, localhost) — the demo adds no
hidden work beyond the shared pipeline.

| probe | family param | median e2e | median server |
|---|---|---:|---:|
| easy | auto | 9,239 ms | 9,236 ms |
| easy-pinned | easy | **661 ms** | 658 ms |
| snow | auto | 3,921 ms | 3,916 ms |
| obstruction | auto | 3,162 ms | 3,157 ms |
| split | auto | 12,398 ms | 12,394 ms |
| strippy | auto | 26,019 ms | 26,015 ms |
| dark-on-dark | auto | 5,096 ms | 5,092 ms |

**Overall median (auto, the browser default): 7,109 ms — the JOBS.md bar
of ≤ 10 s is MET.**

## What the numbers say, honestly

1. **The bar passes on the median, not on every case.** split (12.4 s)
   and strippy (26.0 s) in auto mode exceed 10 s. The aggregate is true;
   the per-family breakdown is here so nobody quotes one without the
   other.
2. **auto is the tax.** The easy image costs 661 ms when pinned to its
   family and 9.2 s under auto, because auto runs every family chain and
   keeps the best — its latency is the slowest chain's latency. The UI
   says this: pick a family when you know it, use auto when you don't
   and can wait.
3. **The demo is the pipeline.** /ocr calls typer.recognise →
   reader.read_chain, the same code path as the CLI; the HTML page adds
   upload + JSON only. The server_ms column exists to prove the gap.

## Reproduce

    python3 tools/demo_latency.py --repeats 7      # this table
    python3 tools/demo_server.py --port 8420       # the demo itself

Fix path for the slow chains is S2/S6 work (faster strippy/split
processing or a cheap pre-classifier to skip chains), not demo work.
