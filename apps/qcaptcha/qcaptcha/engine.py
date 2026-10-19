#!/usr/bin/env python3
"""qcaptcha engine bridge — the SHIPPING superocr read path, nothing else.

One read = baseline.read_text(image, None) followed by
tools/lex_projection.fix_line(text) — byte-for-byte the call the canonical
receipts are bound to (same as webapp /api/ocr route="lex"). No new reader,
no tuning, no cloud.

Engine discovery, in order:
  1. --engine PATH / QCAPTCHA_ENGINE env (a superocr checkout root or a
     standalone bundle root — both contain baseline.py at the top)
  2. walk up from this file (works when running from a source checkout or
     from inside a built bundle)

Bundled-fonts behaviour (carried from W2 PR #82): if the engine root has a
`fonts/` directory with DejaVu TTFs, generation and matching prefer those
when the system has none — the same eight faces, no silent bitmap fallback.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image


class EngineError(RuntimeError):
    pass


def find_engine(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("QCAPTCHA_ENGINE"):
        candidates.append(Path(os.environ["QCAPTCHA_ENGINE"]))
    here = Path(__file__).resolve()
    # qcaptcha/engine.py -> package's parent (bundle root), then walk up
    # (source checkout: apps/qcaptcha/qcaptcha/engine.py -> repo root is +2 more)
    candidates += [here.parent.parent, here.parent.parent.parent,
                   here.parent.parent.parent.parent]
    for c in candidates:
        p = Path(c).resolve()
        if (p / "baseline.py").is_file() and (p / "tools" / "lex_projection.py").is_file():
            return p
    raise EngineError(
        "cannot find the superocr reader (need baseline.py + tools/lex_projection.py). "
        "Pass --engine /path/to/superocr (or the unzipped bundle root), or set QCAPTCHA_ENGINE."
    )


class ReaderEngine:
    """Loads the reader once; read() is then a warm in-process call."""

    def __init__(self, root: str | Path | None = None):
        self.root = find_engine(str(root) if root else None)
        sys.path.insert(0, str(self.root))
        sys.path.insert(0, str(self.root / "tools"))
        try:
            import baseline as _baseline  # noqa: E402
            import generator as _gen  # noqa: E402
            from lex_projection import fix_line  # noqa: E402
        except Exception as e:
            raise EngineError(f"engine at {self.root} failed to import: {e}") from e
        self._baseline = _baseline
        self._gen = _gen
        self._fix_line = fix_line
        self.fonts_used = self._apply_bundled_fonts()

    def _apply_bundled_fonts(self) -> list[str]:
        """If system DejaVu faces are missing but the bundle ships some, use them.

        Mirrors the PR #82 generator fix; kept runtime-side as well so a source
        checkout next to a models/fonts folder behaves the same.
        """
        local = self.root / "fonts"
        have_system = bool(self._gen.available_fonts())
        if local.is_dir():
            bundled = sorted(str(p) for p in local.glob("*.ttf"))
            if bundled and not have_system:
                original = list(getattr(self._gen, "_FONT_CANDIDATES", []))
                seen = {Path(p).name for p in original}
                extra = [p for p in bundled if Path(p).name not in seen]
                self._gen._FONT_CANDIDATES = original + extra
                return self._gen.available_fonts()
        return self._gen.available_fonts()

    def read(self, image: Image.Image) -> tuple[str, float]:
        """Read one captcha image. Returns (lex-cleaned text, avg confidence).

        Exactly the shipping call: read_text(img, None) -> fix_line(text).
        conf is the per-glyph list from the floor; we report its mean (0.0 when
        empty), same convention as webapp /api/ocr avg_confidence.
        """
        raw, conf = self._baseline.read_text(image.convert("RGB"), None)
        avg = round(sum(conf) / len(conf), 3) if conf else 0.0
        return self._fix_line(str(raw).strip()), float(avg)

    def read_with_retry(self, image: Image.Image, retry_upscale: bool = True) -> dict:
        """One honest read attempt; one 2x upscale retry only if the first is empty."""
        text, conf = self.read(image)
        out = {"text": text, "conf": conf, "retried": False, "attempts": 1}
        if not text.strip() and retry_upscale:
            big = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
            text2, conf2 = self.read(big)
            out.update(text=text2, conf=conf2, retried=True, attempts=2)
        return out

    def selftest(self, n: int = 6, seed_base: int = 90210) -> dict:
        """SMOKE ONLY: read n freshly generated in-distribution captchas.

        This proves the wiring (generator -> reader -> lex) end to end on this
        machine. It is NOT a benchmark: not the canonical suites, small n,
        no 98/95 claim.
        """
        rows, ok = [], 0
        for i in range(n):
            img, label = self.generate_sample(seed_base + i)
            text, conf = self.read(img)
            hit = text == label
            ok += hit
            rows.append({"i": i, "want": label, "got": text, "conf": round(conf, 4), "exact": hit})
        return {"items": rows, "exact": ok, "n": n,
                "note": "SMOKE (in-distribution, small n) — not a benchmark; canonical "
                        "suites are evaluation-only"}

    def generate_sample(self, seed: int, family: str = "easy") -> tuple[Image.Image, str]:
        """A fresh captcha image + label via the repo's own generator — used for
        the smoke selftest and by tests. Never touches canonical suite seeds."""
        try:
            img, label = self._gen.generate_one(family, seed, 0)
        except KeyError as e:
            raise EngineError(f"unknown generator family {family!r}: {e}") from e
        return img, str(label)
