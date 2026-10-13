#!/usr/bin/env python3
"""Latency receipt harness for the webapp OCR path (t-20261013-c395).

Hammers POST /api/ocr on a RUNNING webapp server with generated images
(seeded, one per family — same seeds as tools/demo_latency.py) and reports
server_ms / e2e medians plus the worst round trip seen. Two honesty notes:

- the reader is deterministic, so exact-counts are 0/N or N/N per seed; this
  receipt is about LATENCY of the webapp path, not accuracy (accuracy has its
  own stamped benches). The got/label pair is recorded per family anyway.
- the FIRST call after server start pays model/font warm-up (cold start);
  run with --cold to measure that separately, or just read worst_e2e_ms.

Usage: python3 webapp/latency_probe.py [--url http://localhost:8421]
       [--repeats 5] [--out reports/webapp-latency.json]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generator as G  # noqa: E402

SEEDS = {"easy": 11, "snow": 12, "obstruction": 13,
         "split": 14, "strippy": 15, "dark-on-dark": 16}
BAR_MS = 10_000.0  # JOBS.md S9


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8421")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default="reports/webapp-latency.json")
    a = ap.parse_args()

    rows = []
    for fam, seed in SEEDS.items():
        img, label = G.generate_one(fam, seed)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        payload = json.dumps({"image": base64.b64encode(buf.getvalue()).decode(),
                              "family": "auto"}).encode()
        srv, e2e, got = [], [], ""
        for _ in range(a.repeats):
            t0 = time.perf_counter()
            req = urllib.request.Request(a.url + "/api/ocr", data=payload,
                                         headers={"Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=120))
            e2e.append((time.perf_counter() - t0) * 1000)
            srv.append(d["server_ms"])
            got = d["text"]
        rows.append({"family": fam, "seed": seed, "label": label, "got": got,
                     "exact": got == label,
                     "server_ms_median": round(statistics.median(srv), 1),
                     "e2e_ms_median": round(statistics.median(e2e), 1),
                     "e2e_ms_max": round(max(e2e), 1)})
        print(rows[-1])

    worst = max(r["e2e_ms_max"] for r in rows)
    out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "endpoint": "POST /api/ocr (webapp/server.py — same T.recognise "
                       "path as the CLI; nothing re-implemented)",
           "repeats": a.repeats, "rows": rows,
           "server_ms_median_of_medians":
               statistics.median(r["server_ms_median"] for r in rows),
           "worst_e2e_ms": worst, "bar_ms": BAR_MS,
           "bar_met": worst < BAR_MS,
           "note": "deterministic reader: exact is 0/N or N/N per seed; this "
                   "receipt measures the webapp HTTP path, not accuracy"}
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nserver_ms median-of-medians {out['server_ms_median_of_medians']} "
          f"| worst e2e {worst} ms | bar {BAR_MS} ms -> "
          f"{'MET' if out['bar_met'] else 'NOT MET'}")
    print(f"receipt -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
