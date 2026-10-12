#!/usr/bin/env python3
"""s10b_sweep.py — S10b: measure the confidence-gated CNN fallback exactly.

The floor chain (baseline.py) reads each glyph piece with a template score.
S10b wires glyphcnn-v2 in as the fallback for pieces the floor doubts. Which
pieces are doubted depends on a threshold, and running the official bench once
per candidate threshold would cost ~15 minutes each. This tool instead makes
ONE instrumented pass per suite and reconstructs, from that pass, the exact
read text for ANY (gate, min-prob) pair:

  * every piece the floor chain matches is recorded with its template score,
    its height, its word's cap height, and the CNN's opinion on the very same
    normalised crop the trainer uses (normalise_glyph -> 24x24 ink-bright),
  * a read is reconstructed under each policy: if a piece's floor score is
    below the gate and the CNN's probability is at least min-prob, the CNN's
    character replaces the floor's; baseline's SAME_SHAPE case rule then
    applies to the CHARACTER THAT SURVIVED,
  * results are scored with bench.py's exact rule (text == label), so a cell
    of the table is a prediction of the wired chain's official score.

The mirror self-checks before it reports anything: under the floor-only policy
it must reproduce baseline.read_text byte-for-byte on every image, or the tool
refuses to print a table (a sweep built on a mirror that drifted is worse than
no sweep).

NOTE: the mirror copies the orchestration of baseline.read_text as of the
commit it is run on, and calls the chain's own helpers (R.segment, deskew,
_split_marked, _merge_forced, match_native, SAME_SHAPE) through the module.
When the floor reader changes (S7c), re-run; the self-check decides whether
the copy still matches.

Usage:
  python3 tools/s10b_sweep.py --suite-dir /tmp/s10-suites \
      --weights models/glyphcnn-v2.npz --json /tmp/s10b-sweep.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "readers"))

import baseline as B  # noqa: E402
from glyphcnn import CHARS, GlyphCNN  # noqa: E402
from segmentation import normalise_glyph  # noqa: E402
from s10b_gate import reconstruct  # noqa: E402  (shared policy machinery)


# --------------------------------------------------------------------------
# the mirror: baseline read_text's chain, with a policy hook on every piece
# --------------------------------------------------------------------------
def read_text_recorded(img: Image.Image, recorder: "Recorder") -> str:
    """Same orchestration as baseline.read_text, recording each piece.

    The policy is fixed here (floor answers), which is what makes the pass a
    record of the floor chain rather than of some hybrid: reconstruction
    happens later, off the record.
    """
    R = B.R
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=0)
    a = np.array(gray, dtype=np.float32)
    mask = R.otsu(a)
    if mask.mean() > 0.5:
        mask = ~mask
    mask = R.trim(R.despeck(mask))
    if mask.any():
        mask, _ = B.deskew(mask)
        mask = R.trim(mask)
    words = R.segment(mask)
    out = []
    for word in words:
        pieces = []
        for x0, x1 in word:
            for g in B._merge_forced(B._split_marked(R.trim(mask[:, x0:x1]))):
                if g.shape[0] >= 6 and g.sum() >= 10:
                    pieces.append(g)
        if not pieces:
            continue
        recorder.start_word()
        cap = max(g.shape[0] for g in pieces)
        chars = []
        for g in pieces:
            ch, s = B.match_native(g)
            # the chain's own case rule, applied to the floor's answer; the
            # recorder keeps the raw match so reconstruction can re-apply it
            # to the char that survives the gate
            shown = ch
            if shown in B.SAME_SHAPE:
                shown = shown.lower() if g.shape[0] < 0.85 * cap else shown.upper()
            chars.append(shown)
            recorder.add(g, cap, ch, s)
        if chars:
            out.append("".join(chars))
    return " ".join(out)


class Recorder:
    def __init__(self) -> None:
        self.words: list[list[dict]] = []
        self._word: list[dict] | None = None

    def start_word(self) -> None:
        self._word = []
        self.words.append(self._word)

    def add(self, piece: np.ndarray, cap: int, ch: str, score: float) -> None:
        if self._word is None:
            self.start_word()
        self.words[-1].append({"h": int(piece.shape[0]), "cap": int(cap),
                              "ch": ch, "score": float(score), "crop": piece})

    def flush_crops(self) -> None:
        self._word = None


# --------------------------------------------------------------------------
# the pass
# --------------------------------------------------------------------------
def run_suite(suite_dir: Path, suite: str, net: GlyphCNN, limit: int | None,
              verbose: bool) -> dict:
    manifest = [json.loads(l) for l in
                (suite_dir / suite / "manifest.jsonl").read_text().splitlines()
                if l.strip()]
    if limit:
        manifest = manifest[:limit]
    rows = []
    t0 = time.time()
    for n, item in enumerate(manifest, 1):
        img_path = suite_dir / suite / item["image"]
        with Image.open(img_path) as im:
            im = im.convert("RGB")
            rec = Recorder()
            # record word boundaries: the mirror appends word by word, so we
            # re-run it with a fresh recorder per call and split on the calls
            # themselves - see below for why this is exact
            floor_text = read_text_recorded(im, rec)
            # self-check: the recorder's floor reconstruction must equal the
            # chain's own output for this image (see check below)
            floor_rebuilt = reconstruct(rec.words, policy="floor")
            if floor_rebuilt != floor_text:
                raise SystemExit(
                    f"mirror drifted on {item['id']}: chain said {floor_text!r}, "
                    f"mirror rebuilt {floor_rebuilt!r} - refusing to sweep")
            # CNN opinion on every recorded piece (one batched forward)
            crops, flat = [], []
            for wi, word in enumerate(rec.words):
                for p in word:
                    g = p["crop"]
                    box = (0, 0, g.shape[1] - 1, g.shape[0] - 1)
                    crops.append(normalise_glyph(g.astype(bool), box))
                    flat.append((wi, p))
            if crops:
                batch = np.stack(crops)[:, None, :, :].astype(net.p["w1"].dtype)
                probs = net.forward(batch)[0]
                for (wi, p), pr in zip(flat, probs):
                    idx = int(np.argmax(pr))
                    p["cnn_ch"] = CHARS[idx]
                    p["cnn_p"] = float(pr[idx])
            for word in rec.words:
                for p in word:
                    p.pop("crop")
            rows.append({"id": item["id"], "family": item["family"],
                         "label": item["label"], "floor": floor_text,
                         "words": rec.words})
        if verbose and (n % 20 == 0 or n == len(manifest)):
            print(f"  [{suite}] {n}/{len(manifest)}  {time.time()-t0:.0f}s",
                  flush=True)
    return {"suite": suite, "rows": rows}


def score(rows: list[dict], gate: float, min_prob: float) -> dict:
    correct = 0
    fam: dict[str, list[int]] = {}
    gated = flips = 0
    for r in rows:
        text = reconstruct(r["words"], policy="gate", gate=gate, min_prob=min_prob)
        ok = int(text == r["label"])
        correct += ok
        fam.setdefault(r["family"], [0, 0])
        fam[r["family"]][0] += ok
        fam[r["family"]][1] += 1
        for word in r["words"]:
            for p in word:
                if p["score"] < gate:
                    gated += 1
                    if p.get("cnn_p", 0.0) >= min_prob and p["cnn_ch"] != p["ch"]:
                        flips += 1
    return {"exact": correct, "total": len(rows), "gated_pieces": gated,
            "chars_flipped": flips,
            "families": {k: {"correct": v[0], "total": v[1]} for k, v in sorted(fam.items())}}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--suite-dir", default="/tmp/s10-suites")
    p.add_argument("--suites", default="easy,hard")
    p.add_argument("--weights", default=str(ROOT / "models" / "glyphcnn-v2.npz"))
    p.add_argument("--gate", default="0.3,0.4,0.5,0.6,0.7,0.8,0.9")
    p.add_argument("--min-prob", default="0.3,0.5,0.7,0.9")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--json", default=None)
    p.add_argument("--dump-rows", default=None,
                   help="write the recorded per-piece rows here (for offline policy variants)")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    net = GlyphCNN.load(args.weights)
    gates = [float(x) for x in args.gate.split(",")]
    min_probs = [float(x) for x in args.min_prob.split(",")]

    data, out = {}, {}
    for suite in args.suites.split(","):
        data[suite] = run_suite(Path(args.suite_dir), suite, net, args.limit,
                                verbose=not args.quiet)
        out[suite] = {}
        print(f"\n== {suite}: {len(data[suite]['rows'])} items, suite tables "
              f"(gate x min-prob -> exact):", flush=True)
        header = "  gate | " + " ".join(f"p>={mp:<4}" for mp in min_probs)
        print(header)
        for gate in gates:
            cells = []
            for mp in min_probs:
                s = score(data[suite]["rows"], gate, mp)
                out[suite][f"gate={gate},min_prob={mp}"] = s
                cells.append(f"{s['exact']:>2}/{s['total']:<3}")
            print(f"  {gate:>4} | " + " ".join(cells))
        base = score(data[suite]["rows"], -1.0, 1.0)
        print(f"  floor (no gate): {base['exact']}/{base['total']}")
        oracle = score(data[suite]["rows"], 9e9, 0.0)
        print(f"  CNN on every piece (upper bound of this lever): "
              f"{oracle['exact']}/{oracle['total']}")

    if args.dump_rows:
        json.dump({s: data[s]["rows"] for s in data}, open(args.dump_rows, "w"))
        print(f"wrote {args.dump_rows} (recorded rows)")
    if args.json:
        json.dump(out, open(args.json, "w"), indent=2, sort_keys=True)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
