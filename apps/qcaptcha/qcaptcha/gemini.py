#!/usr/bin/env python3
"""qcaptcha Gemini integration — reading + auto-calibration via Google's API.

Two jobs, one client:
  read_captcha(image)   -> the text in a captured captcha image (vision OCR)
  detect_regions(image) -> pixel boxes for the CAPTCHA image and the text box
                           on a full-screen screenshot (auto-calibration)

Key handling (read this before touching anything):
  * keys come from a LOCAL file (default ~/.qcaptcha-keys.json, mode 600) or
    environment (QCAPTCHA_GEMINI_KEYS / GEMINI_API_KEY / GOOGLE_API_KEY).
    This file is never read from the repo, never written to the repo, never
    logged, never sent over the agency wires.
  * the key is sent in the x-goog-api-key HEADER (never in a URL — URLs leak
    into logs and proxies).
  * the pool rotates round-robin; a key that returns 429/403 is parked for a
    cooldown (per-minute quotas reset), 503 parks it briefly; the client walks
    models too (newest stable flash first) because availability varies.
  * every error message is scrubbed of key material before it is raised or
    logged (scrub()).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"

DEFAULT_MODELS = ["gemini-3-flash-preview", "gemini-flash-latest", "gemini-3.5-flash",
                  "gemini-2.5-flash"]
DEFAULT_KEYS_FILE = "~/.qcaptcha-keys.json"

READ_PROMPT = (
    "Read the text in this CAPTCHA image. Reply with ONLY the characters exactly "
    "as shown (preserve letter case and digits). No explanation, no quotes."
)
DETECT_PROMPT = (
    "This is a screenshot of a web page. Locate two elements:\n"
    "1) the CAPTCHA image (a small picture containing distorted letters/digits)\n"
    "2) the text input field where a user would type the captcha answer "
    "(usually a wide white box, often under a label)\n"
    'Return ONLY JSON: {"captcha_box_2d": [ymin,xmin,ymax,xmax], '
    '"input_box_2d": [ymin,xmin,ymax,xmax]} with coordinates normalized to '
    "0-1000 relative to the full image."
)


class GeminiError(RuntimeError):
    pass


class NoKeysError(GeminiError):
    pass


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------

def mask(key: str) -> str:
    """Never show more than the head of a key."""
    k = str(key)
    return (k[:8] + "…" + k[-3:]) if len(k) > 14 else "…"


def scrub(text: str, keys: list[str]) -> str:
    out = str(text)
    for k in keys:
        if k and k in out:
            out = out.replace(k, mask(k))
    return out


def load_keys(path: str | Path | None = None, env: dict | None = None) -> list[str]:
    """Keys from a local JSON file ({'gemini': [...]}) or plain-lines file,
    then from environment variables. File wins (it is the explicit config)."""
    env = env if env is not None else os.environ
    keys: list[str] = []
    p = Path(path).expanduser() if path else Path(DEFAULT_KEYS_FILE).expanduser()
    if p.is_file():
        try:
            raw = p.read_text()
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    for k in ("gemini", "keys", "api_keys"):
                        v = data.get(k)
                        if isinstance(v, list):
                            keys += [str(x).strip() for x in v if str(x).strip()]
                            break
                    else:
                        keys += [str(v).strip() for v in data.values()
                                 if isinstance(v, str) and v.strip()]
                elif isinstance(data, list):
                    keys += [str(x).strip() for x in data if str(x).strip()]
            except json.JSONDecodeError:
                keys += [ln.strip() for ln in raw.splitlines()
                         if ln.strip() and not ln.strip().startswith("#")]
        except OSError:
            pass
    for var in ("QCAPTCHA_GEMINI_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = env.get(var)
        if v:
            keys += [x.strip() for x in re.split(r"[,\n]", v) if x.strip()]
    # de-dup, keep order
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def save_keys(keys: list[str], path: str | Path | None = None) -> Path:
    p = Path(path).expanduser() if path else Path(DEFAULT_KEYS_FILE).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"gemini": [k.strip() for k in keys if k.strip()]},
                         indent=2) + "\n"
    p.write_text(payload)
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return p


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

class GeminiClient:
    """Round-robin key pool + model fallback. Thread-safe."""

    def __init__(self, keys: list[str] | None = None, models: list[str] | None = None,
                 keys_file: str | Path | None = None, timeout: float = 45.0):
        self.keys = list(keys) if keys is not None else load_keys(keys_file)
        self.models = list(models) if models else list(DEFAULT_MODELS)
        self.timeout = float(timeout)
        self._lock = threading.Lock()
        self._next = 0                      # round-robin cursor
        self._cooldown: dict[str, float] = {}   # key -> epoch when usable again
        self._model_cooldown: dict[str, float] = {}

    # -- pool bookkeeping ------------------------------------------------
    def key_count(self) -> int:
        return len(self.keys)

    def _park(self, key: str, seconds: float) -> None:
        self._cooldown[key] = time.time() + float(seconds)

    def _park_model(self, model: str, seconds: float) -> None:
        self._model_cooldown[model] = time.time() + float(seconds)

    def _take_key(self) -> tuple[str | None, float]:
        """Next usable key (round-robin). None + wait time if all cooling."""
        with self._lock:
            n = len(self.keys)
            if n == 0:
                return None, 0.0
            now = time.time()
            soonest = None
            for i in range(n):
                idx = (self._next + i) % n
                k = self.keys[idx]
                ready = self._cooldown.get(k, 0.0)
                if ready <= now:
                    self._next = (idx + 1) % n
                    return k, 0.0
                soonest = ready if soonest is None else min(soonest, ready)
            return None, max(0.0, (soonest or now) - now)

    # -- one HTTP call ---------------------------------------------------
    def _post(self, model: str, key: str, body: dict) -> dict:
        req = urllib.request.Request(f"{API}/models/{model}:generateContent",
                                     data=json.dumps(body).encode(), method="POST")
        req.add_header("x-goog-api-key", key)   # header, NEVER the URL
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:
                pass
            raise GeminiHttpError(e.code, scrub(str(detail), self.keys)) from None
        except Exception as e:  # timeouts, DNS, TLS…
            raise GeminiError(scrub(f"{type(e).__name__}: {e}", self.keys)) from None

    def generate(self, parts: list[dict], *, max_output_tokens: int = 512,
                 deadline_s: float | None = None) -> str:
        """One vision request with key+model rotation. Returns the text."""
        if not self.keys:
            raise NoKeysError(
                "no Gemini API keys configured. Add them in the app's Keys… dialog, "
                "or create ~/.qcaptcha-keys.json with {\"gemini\": [\"key1\", \"key2\"]}, "
                "or set QCAPTCHA_GEMINI_KEYS.")
        deadline = time.time() + (deadline_s if deadline_s is not None
                                  else max(30.0, self.timeout * 2))
        errors: list[str] = []
        while time.time() < deadline:
            key, wait = self._take_key()
            if key is None:
                if wait <= 0 or time.time() + wait > deadline:
                    break
                time.sleep(min(wait, 5.0))
                continue
            for model in list(self.models):
                if self._model_cooldown.get(model, 0.0) > time.time():
                    continue
                body = {
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "maxOutputTokens": int(max_output_tokens),
                        # Gemini 3 thinks by default and that eats the output
                        # budget; a captcha read needs zero thinking.
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                }
                try:
                    d = self._post(model, key, body)
                except GeminiHttpError as e:
                    if e.code == 429 or e.code == 403:
                        self._park(key, 65)          # per-minute quota; next key
                        errors.append(f"{model}: key {mask(key)} throttled")
                        break                        # next key, same model order
                    if e.code == 503:
                        self._park_model(model, 20)  # high demand; try next model
                        errors.append(f"{model}: unavailable (503)")
                        continue
                    if e.code == 400 and "thinking" in e.message.lower():
                        body["generationConfig"].pop("thinkingConfig", None)
                        try:
                            d = self._post(model, key, body)
                        except GeminiHttpError as e2:
                            errors.append(f"{model}: {e2.message[:80]}")
                            continue
                    elif e.code == 404:
                        self._park_model(model, 600)  # model retired for this key
                        errors.append(f"{model}: not available")
                        continue
                    else:
                        errors.append(f"{model}: HTTP {e.code} {e.message[:80]}")
                        continue
                except GeminiError as e:
                    errors.append(f"{model}: {str(e)[:100]}")
                    break                            # network problem: next key
                try:
                    cand = d["candidates"][0]
                    txt = "".join(p.get("text", "") for p in cand["content"]["parts"])
                except Exception:
                    errors.append(f"{model}: no candidates in response")
                    continue
                if txt.strip():
                    return txt.strip()
                errors.append(f"{model}: empty reply")
        raise GeminiError("all keys/models failed — " + ("; ".join(errors[-6:]) or "no keys"))


class GeminiHttpError(GeminiError):
    def __init__(self, code: int, message: str):
        super().__init__(f"HTTP {code}: {message}")
        self.code = int(code)
        self.message = message


# ---------------------------------------------------------------------------
# the two high-level jobs
# ---------------------------------------------------------------------------

def _img_png_b64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


_QUOTE_TRIM = "\"'`“”‘’ \t\r\n"


def parse_read_reply(text: str) -> str:
    """First line, unquoted, backticks stripped. Empty string if nothing."""
    if not text:
        return ""
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    line = line.strip(_QUOTE_TRIM)
    if line.lower().startswith("the text is"):
        line = line.split(":", 1)[-1].strip(_QUOTE_TRIM)
    return line


def read_captcha(client: GeminiClient, img) -> tuple[str, float | None]:
    """Read the captcha image via Gemini. Returns (text, wall_seconds)."""
    t0 = time.time()
    txt = client.generate([{"text": READ_PROMPT},
                           {"inline_data": {"mime_type": "image/png",
                                            "data": _img_png_b64(img)}}])
    return parse_read_reply(txt), time.time() - t0


_BOX_KEYS = {
    "captcha": ("captcha_box_2d", "captcha_box", "captcha", "captcha_image_box",
                "image_box", "captchaimage_box_2d"),
    "input": ("input_box_2d", "input_box", "text_box_2d", "text_box", "textbox",
              "entry_box", "input_field_box_2d", "input"),
}


def _find_box(text: str, names: tuple[str, ...]) -> list[int] | None:
    for name in names:
        m = re.search(r'"%s"\s*:\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)'
                      r'\s*\]' % re.escape(name), text)
        if m:
            return [int(x) for x in m.groups()]
    return None


def parse_detect_reply(text: str, size) -> dict:
    """Reply -> {'captcha': [x,y,w,h] | None, 'input': [x,y,w,h] | None} in pixels.

    Accepts the documented 0-1000 normalized ymin/xmin/ymax/xmax form. A reply
    is read as raw pixels only when some value is clearly beyond the normalized
    range (max > 1200 — slack so a sloppy 1005 stays normalized). Boxes are
    clamped to the image; results smaller than 8px are dropped.
    """
    W, H = int(size[0]), int(size[1])
    out: dict[str, list[int] | None] = {"captcha": None, "input": None}
    for role, names in _BOX_KEYS.items():
        box = _find_box(text, names)
        if not box:
            continue
        a, b, c, d = box
        pixel_mode = max(abs(a), abs(b), abs(c), abs(d)) > 1200
        if pixel_mode:
            ymin, xmin, ymax, xmax = a, b, c, d
        else:
            ymin = a / 1000 * H
            xmin = b / 1000 * W
            ymax = c / 1000 * H
            xmax = d / 1000 * W
        x0, x1 = sorted((xmin, xmax))
        y0, y1 = sorted((ymin, ymax))
        x0 = max(0, min(int(round(x0)), W))
        y0 = max(0, min(int(round(y0)), H))
        x1 = max(0, min(int(round(x1)), W))
        y1 = max(0, min(int(round(y1)), H))
        w, h = x1 - x0, y1 - y0
        if w < 8 or h < 8:
            continue
        out[role] = [x0, y0, w, h]
    return out


def detect_regions(client: GeminiClient, screenshot) -> dict:
    """Ask Gemini where the captcha and the input box are on a screenshot."""
    txt = client.generate([{"text": DETECT_PROMPT},
                           {"inline_data": {"mime_type": "image/png",
                                            "data": _img_png_b64(screenshot)}}],
                          max_output_tokens=400)
    return parse_detect_reply(txt, screenshot.size)


SOLVE_PROMPT = (
    "You are looking at a screenshot of a desktop with a CAPTCHA challenge on it. "
    "Do two things: (1) locate the captcha image and the text input box where the "
    "answer must be typed; (2) read the captcha characters exactly as they appear "
    "(keep capital/lowercase exactly; no spaces unless visible). "
    "Reply with minified JSON only, no prose: "
    '{"captcha_box_2d":[ymin,xmin,ymax,xmax],"input_box_2d":[ymin,xmin,ymax,xmax],'
    '"text":"<the captcha characters>"} '
    "Boxes are 0-1000 normalized coordinates. If the captcha is not visible, use "
    'null for its box and "" for the text.'
)


def parse_solve_reply(text: str, size) -> dict:
    """One reply -> {'captcha': [x,y,w,h]|None, 'input': [x,y,w,h]|None, 'text': str}.

    Box parsing is exactly parse_detect_reply's (same tolerances). Text is pulled
    from the JSON "text" field with the read-cleanup applied."""
    boxes = parse_detect_reply(text, size)
    t = ""
    m = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if m:
        raw = m.group(1)
        if "\\" in raw:                      # decode JSON escapes properly —
            try:                               # unicode_escape would mangle
                raw = json.loads('"' + raw + '"')   # non-ASCII (accents) instead
            except Exception:
                pass
        t = parse_read_reply(raw)
    return {"captcha": boxes["captcha"], "input": boxes["input"], "text": t}


def solve_page(client: GeminiClient, screenshot, *, hint: dict | None = None) -> dict:
    """Find both boxes AND read the captcha in ONE request.

    This is what makes per-captcha recalibration free: the box we crop is the box
    the model just reported, so a captcha that changes size or moves between
    refreshes needs no manual recalibration. `hint` may carry the last known
    regions (`{"captcha": [x,y,w,h], "input": [x,y,w,h]}`) — the model is told
    they are only a hint, because stale hints are exactly the problem here."""
    prompt = SOLVE_PROMPT
    if hint and hint.get("captcha"):
        x, y, w, h = [int(v) for v in hint["captcha"]]
        prompt += (f" Hint (may be stale — verify): the captcha was last seen around "
                   f"x={x}, y={y}, w={w}, h={h} pixels.")
    t0 = time.time()
    txt = client.generate([{"text": prompt},
                           {"inline_data": {"mime_type": "image/png",
                                            "data": _img_png_b64(screenshot)}}],
                          max_output_tokens=400)
    out = parse_solve_reply(txt, screenshot.size)
    out["seconds"] = round(time.time() - t0, 2)
    return out


def probe_keys(client: GeminiClient, limit: int | None = None) -> dict:
    """Cheap validation of every key (models list). Never reveals key material."""
    results = []
    for i, k in enumerate(client.keys[:limit] if limit else client.keys):
        req = urllib.request.Request(f"{API}/models?pageSize=1")
        req.add_header("x-goog-api-key", k)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                json.loads(r.read())
            results.append({"index": i, "key": mask(k), "ok": True, "status": 200})
        except urllib.error.HTTPError as e:
            results.append({"index": i, "key": mask(k), "ok": False, "status": e.code})
        except Exception as e:
            results.append({"index": i, "key": mask(k), "ok": False,
                            "status": 0, "error": scrub(str(e)[:80], client.keys)})
        time.sleep(0.04)  # polite
    ok = sum(1 for r in results if r["ok"])
    return {"valid": ok, "total": len(results), "results": results}
