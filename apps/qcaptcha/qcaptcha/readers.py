#!/usr/bin/env python3
"""qcaptcha readers — one interface, two backends.

    read_with_retry(image, retry_upscale=True) -> {"text", "conf", "retried",
                                                   "attempts", "backend"}

  * LocalReader  — the offline superocr route (baseline.read_text + optional
                   lex projection). conf = mean glyph confidence.
  * GeminiReader — Google Gemini vision OCR (network; the user's own API keys).
                   conf = None (the API gives no comparable score — we do not
                   invent one).

`make_reader(cfg, engine)` picks from config["reader_backend"]; the Gemini
reader falls back to local when no keys are configured, so the app always
starts.
"""
from __future__ import annotations

from . import gemini as gemini_mod


class ReaderError(RuntimeError):
    pass


class LocalReader:
    backend = "local"

    def __init__(self, engine):
        if engine is None:
            raise ReaderError("LocalReader needs the superocr engine")
        self.engine = engine

    def read_with_retry(self, image, retry_upscale: bool = True) -> dict:
        res = dict(self.engine.read_with_retry(image, retry_upscale=retry_upscale))
        res.setdefault("backend", self.backend)
        return res


class GeminiReader:
    backend = "gemini"

    def __init__(self, client: gemini_mod.GeminiClient, engine=None,
                 apply_lex: bool = False):
        if client is None or not client.key_count():
            raise gemini_mod.NoKeysError("GeminiReader needs at least one key")
        self.client = client
        self.engine = engine            # optional: used only when apply_lex
        self.apply_lex = bool(apply_lex)

    def read_page(self, screenshot, hint: dict | None = None) -> dict:
        """Detect + read on ONE full screenshot (single Gemini call).

        Returns {"text", "captcha_box", "input_box", "conf": None, "backend",
        "seconds"} — either box may be None when the model could not find it
        (the caller then falls back to the manually calibrated region)."""
        r = gemini_mod.solve_page(self.client, screenshot, hint=hint)
        return {"text": r.get("text", ""), "captcha_box": r.get("captcha"),
                "input_box": r.get("input"), "conf": None, "backend": self.backend,
                "seconds": r.get("seconds")}

    def read_page(self, screenshot, hint: dict | None = None) -> dict:
        """Detect + read on ONE full screenshot (single Gemini call).

        Returns {"text", "captcha_box", "input_box", "conf": None, "backend",
        "seconds"} — either box may be None when the model could not find it
        (the caller then falls back to the manually calibrated region)."""
        r = gemini_mod.solve_page(self.client, screenshot, hint=hint)
        return {"text": r.get("text", ""), "captcha_box": r.get("captcha"),
                "input_box": r.get("input"), "conf": None, "backend": self.backend,
                "seconds": r.get("seconds")}

    def read_with_retry(self, image, retry_upscale: bool = True) -> dict:
        from PIL import Image

        text, seconds = gemini_mod.read_captcha(self.client, image)
        res = {"text": text, "conf": None, "retried": False, "attempts": 1,
               "backend": self.backend, "seconds": round(seconds, 2)}
        if not text.strip() and retry_upscale:
            big = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
            text2, s2 = gemini_mod.read_captcha(self.client, big)
            res.update(text=text2, retried=True, attempts=2,
                       seconds=round(seconds + s2, 2))
        if self.apply_lex and res["text"].strip() and self.engine is not None:
            try:
                res["text"] = self.engine._fix_line(res["text"])
            except Exception:
                pass                       # lex is best-effort by definition
        return res


def make_reader(cfg: dict, engine=None, *, client=None):
    """Build the configured reader. Returns (reader, note) where note explains
    any fallback that happened (shown in the panel log)."""
    backend = str(cfg.get("reader_backend", "gemini")).lower()
    if backend == "gemini":
        try:
            cl = client or gemini_mod.GeminiClient(
                keys_file=cfg.get("gemini_keys_file") or None,
                models=list(cfg.get("gemini_models") or []) or
                ([cfg["gemini_model"]] if cfg.get("gemini_model") else None),
                timeout=float(cfg.get("gemini_timeout_s", 45.0)))
            return GeminiReader(cl, engine=engine,
                                apply_lex=bool(cfg.get("gemini_apply_lex", False))), ""
        except gemini_mod.NoKeysError as e:
            if engine is None:
                raise
            return LocalReader(engine), f"no Gemini keys ({e}); using local reader"
    if engine is None:
        raise ReaderError("local reader needs the superocr engine (--engine …)")
    return LocalReader(engine), ""
