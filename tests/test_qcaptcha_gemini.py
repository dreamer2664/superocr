#!/usr/bin/env python3
"""qcaptcha Gemini tests.

Unit tests use a fake HTTP layer (client._post) so rotation/fallback logic is
tested deterministically and without quota. Live tests hit the real API only
when keys are present AND QCAPTCHA_LIVE=1 is set:

    QCAPTCHA_LIVE=1 python3 tests/test_qcaptcha_gemini.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps" / "qcaptcha"
sys.path.insert(0, str(APP))

from PIL import Image  # noqa: E402

from qcaptcha import gemini as G  # noqa: E402

KEYS_FILE = os.environ.get("QCAPTCHA_KEYS_FILE", str(Path.home() / ".private" / "gemini-keys.json"))
HAVE_KEYS = Path(KEYS_FILE).is_file()
LIVE = HAVE_KEYS and os.environ.get("QCAPTCHA_LIVE") == "1"


class TestKeys(unittest.TestCase):
    def test_load_from_json_file_dict_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "k.json"
            p.write_text(json.dumps({"gemini": ["k1", "k2", "k1"]}))
            self.assertEqual(G.load_keys(p, env={}), ["k1", "k2"])   # de-dup, order kept
            p.write_text(json.dumps(["a1", "a2"]))
            self.assertEqual(G.load_keys(p, env={}), ["a1", "a2"])

    def test_load_from_plain_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "k.txt"
            p.write_text("# comment\nx1\n\nx2\n")
            self.assertEqual(G.load_keys(p, env={}), ["x1", "x2"])

    def test_env_vars_and_dedup(self):
        env = {"QCAPTCHA_GEMINI_KEYS": "e1,e2", "GEMINI_API_KEY": "e2"}
        self.assertEqual(G.load_keys(Path("/nonexistent"), env=env), ["e1", "e2"])

    def test_save_keys_mode_600(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = G.save_keys(["s1", " s2 "], Path(tmp) / "deep" / "k.json")
            self.assertEqual(json.loads(p.read_text()), {"gemini": ["s1", "s2"]})
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_mask_and_scrub(self):
        # synthetic fixture only — real keys must never be committed
        key = "AQ.FAKEKEYFAKEKEYFAKEKEYFAKEKEYFAKEKEYFAKEFAKE"
        self.assertNotIn(key[12:], G.mask(key))
        msg = f"HTTP 400 for key {key} bad"
        scrubbed = G.scrub(msg, [key])
        self.assertNotIn(key, scrubbed)
        self.assertIn("AQ.FAKEK…", scrubbed)


class FakePost:
    """Programmable _post replacement: (model, key) -> response dict or Exception."""

    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = []

    def __call__(self, model, key, body):
        self.calls.append((model, key))
        out = self.behavior(model, key, len(self.calls))
        if isinstance(out, Exception):
            raise out
        return out

    @staticmethod
    def reply(text):
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def make_client(keys=("k1", "k2", "k3"), models=("m1", "m2")):
    return G.GeminiClient(keys=list(keys), models=list(models), timeout=5.0)


class TestRotation(unittest.TestCase):
    def test_429_parks_key_and_moves_on(self):
        c = make_client()
        def behavior(model, key, n):
            if key == "k1":
                return G.GeminiHttpError(429, "quota")
            return FakePost.reply("hello")
        c._post = FakePost(behavior)
        self.assertEqual(c.generate([{"text": "x"}]), "hello")
        used_keys = [k for _, k in c._post.calls]
        self.assertEqual(used_keys[0], "k1")          # tried first, throttled
        self.assertIn("k2", used_keys)                # moved on
        self.assertGreater(c._cooldown.get("k1", 0), time.time())   # parked

    def test_503_parks_model_not_key(self):
        c = make_client(keys=("k1",), models=("m1", "m2"))
        def behavior(model, key, n):
            if model == "m1":
                return G.GeminiHttpError(503, "high demand")
            return FakePost.reply("ok2")
        c._post = FakePost(behavior)
        self.assertEqual(c.generate([{"text": "x"}]), "ok2")
        self.assertGreater(c._model_cooldown.get("m1", 0), time.time())
        self.assertNotIn("k1", c._cooldown)           # key was NOT punished

    def test_all_fail_raises_masked_error(self):
        c = make_client()
        c._post = FakePost(lambda m, k, n: G.GeminiHttpError(429, "quota"))
        with self.assertRaises(G.GeminiError) as ctx:
            c.generate([{"text": "x"}], deadline_s=2.0)
        msg = str(ctx.exception)
        self.assertIn("all keys/models failed", msg)
        for k in ("k1", "k2", "k3"):
            self.assertNotIn(k, msg.replace("key", ""))  # no raw key material

    def test_no_keys_clean_error(self):
        c = G.GeminiClient(keys=[], models=["m"])
        with self.assertRaises(G.NoKeysError):
            c.generate([{"text": "x"}])


class TestParsing(unittest.TestCase):
    def test_read_reply_cleanup(self):
        self.assertEqual(G.parse_read_reply('"Amber42"'), "Amber42")
        self.assertEqual(G.parse_read_reply("`xYz`\nextra"), "xYz")
        self.assertEqual(G.parse_read_reply("  The text is: B0LT \n"), "B0LT")
        self.assertEqual(G.parse_read_reply(""), "")

    def test_detect_normalized_to_pixels(self):
        # the exact reply shape seen from the live model (proven in the Xvfb run)
        text = '{"captcha_box_2d": [75, 31, 262, 437], "input_box_2d": [377, 32, 430, 436]}'
        out = G.parse_detect_reply(text, (1280, 800))
        self.assertEqual(out["captcha"], [40, 60, 519, 150])
        self.assertEqual(out["input"], [41, 302, 517, 42])

    def test_detect_pixel_mode_and_alt_names(self):
        text = '{"captcha_box": [800, 1200, 1020, 1800], "text_box": [800, 1200, 860, 1800]}'
        out = G.parse_detect_reply(text, (1920, 1080))
        self.assertEqual(out["captcha"], [1200, 800, 600, 220])
        self.assertEqual(out["input"], [1200, 800, 600, 60])

    def test_sloppy_normalized_over_1000_stays_normalized(self):
        text = '{"captcha_box_2d": [900, 900, 1050, 1050]}'
        out = G.parse_detect_reply(text, (1280, 800))
        self.assertEqual(out["captcha"], [1152, 720, 128, 80])   # clamped, not pixel-scale

    def test_detect_clamps_and_drops(self):
        # partial box in pixel mode: clamped to the image, kept
        out = G.parse_detect_reply('{"captcha_box_2d": [700, 1200, 900, 1400]}', (1280, 800))
        self.assertEqual(out["captcha"], [1200, 700, 80, 100])
        # fully off-screen pixel box: dropped
        out = G.parse_detect_reply('{"captcha_box_2d": [1300, 1300, 1500, 1500]}', (1280, 800))
        self.assertIsNone(out["captcha"])
        # tiny box: dropped
        out = G.parse_detect_reply('{"input_box_2d": [10, 10, 12, 12]}', (1280, 800))
        self.assertIsNone(out["input"])

    def test_detect_no_boxes(self):
        out = G.parse_detect_reply("I cannot find any captcha here.", (100, 100))
        self.assertEqual(out, {"captcha": None, "input": None})


@unittest.skipUnless(LIVE, "live tests need keys + QCAPTCHA_LIVE=1")
class TestLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        import generator as gen_mod
        cls.gen = gen_mod
        cls.client = G.GeminiClient(keys_file=KEYS_FILE,
                                    models=["gemini-3-flash-preview"])

    def test_keys_probe(self):
        res = G.probe_keys(self.client, limit=4)
        self.assertGreaterEqual(res["valid"], 1)
        for r in res["results"]:
            # probe results must be masked forms — never full key material
            self.assertLessEqual(len(r["key"]), 16)
            self.assertIn("…", r["key"])

    def test_live_read_one_captcha(self):
        img, label = self.gen.generate_one("easy", 777001, 0)
        text, seconds = G.read_captcha(self.client, img)
        self.assertTrue(text)
        self.assertLess(seconds, 30)
        # exact match expected on easy; allow the known 0/O class of ambiguity
        self.assertEqual(text.strip(), label.strip(),
                         f"live read mismatch: want {label!r} got {text!r}")


# ====================================================================== solve
class TestSolveReply(unittest.TestCase):
    """One reply carries both boxes AND the text (the per-captcha auto path)."""

    SIZE = (1280, 800)

    def test_boxes_and_text(self):
        raw = ('{"captcha_box_2d":[75,31,262,437],"input_box_2d":[377,32,430,436],'
               '"text":"sUM 34 DELTA"}')
        out = G.parse_solve_reply(raw, self.SIZE)
        self.assertEqual(out["captcha"], [40, 60, 519, 150])
        self.assertEqual(out["input"], [41, 302, 517, 42])
        self.assertEqual(out["text"], "sUM 34 DELTA")

    def test_text_with_escapes(self):
        out = G.parse_solve_reply('{"captcha_box_2d":null,"input_box_2d":null,'
                                  '"text":"AB\\n12"}', self.SIZE)
        self.assertEqual(out["text"], "AB")   # \n decodes; read path is first-line only
        self.assertIsNone(out["captcha"])

    def test_unicode_text_survives(self):
        out = G.parse_solve_reply('{"captcha_box_2d":null,"input_box_2d":null,'
                                  '"text":"caf\\u00e9"}', self.SIZE)
        self.assertEqual(out["text"], "caf\u00e9")      # \u escape decoded
        out2 = G.parse_solve_reply('{"captcha_box_2d":null,"input_box_2d":null,'
                                   '"text":"caf\u00e9"}', self.SIZE)
        self.assertEqual(out2["text"], "caf\u00e9")     # raw utf-8 untouched

    def test_nulls_and_missing_text(self):
        out = G.parse_solve_reply('{"captcha_box_2d":null,"input_box_2d":null,"text":""}',
                                  self.SIZE)
        self.assertEqual((out["captcha"], out["input"], out["text"]), (None, None, ""))
        out = G.parse_solve_reply('{"captcha_box_2d":[0,0,100,100]}', self.SIZE)
        self.assertEqual(out["text"], "")
        self.assertIsNotNone(out["captcha"])

    def test_pixel_mode_and_clamps_shared_with_detect(self):
        # slack rule: >1200 means the reply is in pixels; values get clamped
        raw = ('{"captcha_box_2d":[60,40,210,1301],"input_box_2d":[300,40,346,1301],'
               '"text":"X7"}')
        out = G.parse_solve_reply(raw, self.SIZE)
        self.assertEqual(out["captcha"], [40, 60, 1240, 150])   # x1 clamped to W
        self.assertEqual(out["input"], [40, 300, 1240, 46])
        # sloppy 1000-ish values stay normalized (the >1200 slack)
        raw2 = '{"captcha_box_2d":[75,31,262,1005],"input_box_2d":[375,32,432,1004]}'
        out2 = G.parse_solve_reply(raw2, self.SIZE)
        # 1005/1000 * W = 1286 -> clamped to the image edge, still normalized
        self.assertEqual(out2["captcha"], [40, 60, 1240, 150])


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls, self.parts, self.kw = reply, 0, None, None

    def generate(self, parts, **kw):
        self.calls += 1
        self.parts, self.kw = parts, kw
        return self.reply


class TestSolvePageCall(unittest.TestCase):
    def test_single_call_with_hint_and_seconds(self):
        from PIL import Image
        shot = Image.new("RGB", (1280, 800), "white")
        cl = FakeClient('{"captcha_box_2d":[75,31,262,437],"input_box_2d":[377,32,430,436],'
                        '"text":"ABC"}')
        out = G.solve_page(cl, shot, hint={"captcha": [10, 20, 30, 40]})
        self.assertEqual(cl.calls, 1)                      # ONE request, not two
        prompt = cl.parts[0]["text"]
        self.assertIn("x=10, y=20", prompt)                # hint present…
        self.assertIn("may be stale", prompt)              # …and labelled as a hint
        self.assertIn("inline_data", cl.parts[1])
        self.assertEqual(out["text"], "ABC")
        self.assertEqual(out["captcha"], [40, 60, 519, 150])
        self.assertIn("seconds", out)

    def test_no_hint_ok(self):
        from PIL import Image
        cl = FakeClient('{"captcha_box_2d":null,"input_box_2d":null,"text":""}')
        out = G.solve_page(cl, Image.new("RGB", (640, 480), "black"))
        self.assertEqual(cl.calls, 1)
        self.assertEqual((out["captcha"], out["input"], out["text"]), (None, None, ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
