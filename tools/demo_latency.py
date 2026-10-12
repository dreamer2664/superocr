#!/usr/bin/env python3
"""Measure the demo's latency honestly (t-20261011-27bc).

Starts tools/demo_server.py on a private port, generates sample images
with the repo's own generator, POSTs each to /ocr REPEATS times, and
reports medians — server-side recognition time and end-to-end — plus the
10-second bar check from JOBS.md. Everything printed is what was measured;
nothing is smoothed or cherry-picked (the per-request numbers are written
to reports/demo-latency.json next to this report).

Usage: python3 tools/demo_latency.py [--repeats 7] [--port 8431]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
import generator as G  # noqa: E402

BAR_MS = 10_000.0  # JOBS.md S9: every auto probe <= 10s


SEEDS = {"easy": 11, "snow": 12, "obstruction": 13,
         "split": 14, "strippy": 15, "dark-on-dark": 16}


def make_samples() -> dict[str, Image.Image]:
    # kept for callers that want one pinned sample per family; the measurement
    # loop generates a distinct image per repeat (SEEDS + 1000*i).
    return {fam: G.generate_one(fam, seed)[0] for fam, seed in SEEDS.items()}


# label -> (family key in samples, family parameter sent to /ocr).
# easy-pinned repeats the easy image with family=easy to measure what
# auto costs on top: the browser default is auto, and auto runs every
# family chain, so the pinned number isolates that overhead honestly.
PROBES = (("easy", "easy", "auto"), ("easy-pinned", "easy", "easy"),
          ("snow", "snow", "auto"), ("obstruction", "obstruction", "auto"),
          ("split", "split", "auto"), ("strippy", "strippy", "auto"),
          ("dark-on-dark", "dark-on-dark", "auto"))


def post(port: int, img: Image.Image, family: str) -> tuple[float, dict]:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    payload = json.dumps({"image": base64.b64encode(buf.getvalue()).decode(),
                          "family": family}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/ocr", data=payload,
        headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    return (time.perf_counter() - t0) * 1000.0, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=7)
    ap.add_argument("--port", type=int, default=8431)
    args = ap.parse_args()

    srv = subprocess.Popen([sys.executable, str(ROOT / "tools" / "demo_server.py"),
                            "--port", str(args.port), "--host", "127.0.0.1"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):  # wait for the port
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/health",
                                            timeout=1):
                    break
            except Exception:
                time.sleep(0.2)
        else:
            sys.exit("server never came up")

        samples = make_samples()
        results = {}
        all_e2e = []
        for label, key, fam_param in PROBES:
            e2e, srv_ms = [], []
            for i in range(args.repeats):
                # s18 (t-...-latency-truth): a DISTINCT image per repeat. The
                # old loop re-sent one image, so repeats 2..n rode warm caches
                # (18 ms vs 531 ms cold on easy) and the median described the
                # cache, not the demo. Seeds stay pinned, so the run is still
                # reproducible from a clean clone.
                seed = SEEDS[key] + 1000 * i
                img = G.generate_one(key, seed)[0]
                ms, body = post(args.port, img, fam_param)
                e2e.append(ms)
                srv_ms.append(body.get("server_ms", 0.0))
            results[label] = {
                "family_param": fam_param,
                "end_to_end_ms": [round(x, 1) for x in e2e],
                "server_ms": [round(x, 1) for x in srv_ms],
                "median_end_to_end_ms": round(statistics.median(e2e), 1),
                "median_server_ms": round(statistics.median(srv_ms), 1),
            }
            if label != "easy-pinned":  # pinned probe is diagnostic, not part of the bar
                all_e2e.extend(e2e)
            print(f"{label:12s} median e2e {statistics.median(e2e):8.0f} ms  "
                  f"median server {statistics.median(srv_ms):8.0f} ms")

        overall = statistics.median(all_e2e)
        # S9 (t-20261012-5c63): the bar is EVERY auto probe under 10 s, not
        # just the pooled median — a 26 s strippy behind a 4 s easy is still
        # a broken demo. The pinned probe stays diagnostic-only.
        over = {label: r["median_end_to_end_ms"]
                for label, r in results.items()
                if label != "easy-pinned" and r["median_end_to_end_ms"] > BAR_MS}
        report = {
            "measurement": "distinct image per repeat (seed = pinned_base + 1000*i); "
                           "same-image warm-cache repeats intentionally NOT the headline",
            "repeats_per_family": args.repeats,
            "families": results,
            "overall_median_end_to_end_ms": round(overall, 1),
            "bar_ms": BAR_MS,
            "bar_met": not over,
            "probes_over_bar_ms": over,
        }
        rep = ROOT / "reports" / "demo-latency.json"
        rep.parent.mkdir(exist_ok=True)
        rep.write_text(json.dumps(report, indent=2) + "\n")
        for label, r in results.items():
            flag = ""
            if label != "easy-pinned":
                ok = r["median_end_to_end_ms"] <= BAR_MS
                flag = f"  [{'ok' if ok else 'OVER BAR'}]"
            print(f"  {label:12s} bar check{flag}")
        print(f"\nOVERALL median end-to-end: {overall:.0f} ms — "
              f"every-probe bar {BAR_MS / 1000:.0f}s "
              f"{'MET' if report['bar_met'] else 'NOT MET'}"
              + (f" (over: {over})" if over else ""))
        print(f"per-request numbers written to {rep.relative_to(ROOT)}")
    finally:
        srv.terminate()
        srv.wait(timeout=5)


if __name__ == "__main__":
    main()
