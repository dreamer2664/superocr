"""Tests for the web dashboard server (t-20261013-c395).

Fast, offline, seeded: the server is started once on an ephemeral port with
tmp fixtures (a 2-item suite, a 3-message bus, a 2-task board); every assert
hits the real HTTP endpoints. The OCR test asserts response SHAPE and timing
fields, not recognition correctness — correctness has its own benches, and a
dashboard test must not flake on a hard seed.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import generator as G  # noqa: E402
import webapp.server as WS  # noqa: E402


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})


def _get_json(url: str):
    status, body, _ = _get(url)
    return status, json.loads(body)


def _post_json(url: str, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("webapp")

    # --- suite fixture: 2 easy items, real generated images
    suite = tmp / "suite-x"
    (suite / "easy" / "images").mkdir(parents=True)
    lines = []
    for i in range(2):
        img, label = G.generate_one("easy", 900 + i)
        p = suite / "easy" / "images" / f"easy-{i:04d}.png"
        img.save(p)
        lines.append(json.dumps({"id": f"easy-{i:04d}",
                                 "image": f"images/easy-{i:04d}.png",
                                 "label": label, "family": "easy",
                                 "tags": ["seeded", f"seed={900 + i}"]}))
    (suite / "easy" / "manifest.jsonl").write_text("\n".join(lines) + "\n")

    # --- bus fixture
    bus = tmp / "bus"
    bus.mkdir()
    msgs = [{"ts": f"2026-10-13T0{i}:00:00Z", "from": f"agent{i}",
             "type": "status", "text": f"line {i}"} for i in range(3)]
    (bus / "general.jsonl").write_text(
        "\n".join(json.dumps(m) for m in msgs) + "\n")

    # --- board fixture
    board = tmp / "board"
    board.mkdir()
    for tid, status in (("t-a", "open"), ("t-b", "done")):
        (board / f"{tid}.json").write_text(json.dumps(
            {"id": tid, "title": f"task {tid}", "status": status,
             "owner": "someone", "pr": None, "priority": 2,
             "updated_ts": "2026-10-13T08:00:00Z"}))

    saved = dict(WS.CONFIG)
    WS.CONFIG["suites"] = [{"name": suite.name, "path": suite}]
    WS.CONFIG["bus_dir"] = bus
    WS.CONFIG["board_dir"] = board

    srv = WS.serve("127.0.0.1", 0)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        WS.CONFIG.update(saved)


def test_index_and_static(server):
    status, body, hdrs = _get(server + "/")
    assert status == 200 and b"superocr" in body
    assert hdrs["Content-Type"].startswith("text/html")
    for f in ("app.js", "style.css"):
        status, body, _ = _get(server + "/static/" + f)
        assert status == 200 and len(body) > 100
    # no traversal through /static/
    status, body, _ = _get(server + "/static/../server.py")
    assert status == 404


def test_health(server):
    status, h = _get_json(server + "/api/health")
    assert status == 200 and h["ok"] is True
    assert h["version"] == WS.VERSION
    assert "glyphcnn-v3.npz" in h["models"]
    assert h["suites_configured"] == ["suite-x"]
    assert h["bus_enabled"] is True and h["board_enabled"] is True


def test_ocr_shape_and_timing(server):
    img, label = G.generate_one("easy", 1234)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    status, d = _post_json(server + "/api/ocr",
                           {"image": b64, "family": "auto", "detail": True})
    assert status == 200
    assert d["route"] == "typer"  # default unchanged
    assert isinstance(d["text"], str) and d["text"]
    assert isinstance(d["family"], str)
    assert 0.0 <= d["avg_confidence"] <= 1.0
    assert d["server_ms"] > 0 and d["server_ms"] < 20000
    # confidences are per glyph (spaces carry none); loose but honest
    assert 1 <= len(d["confidences"]) <= len(d["text"])
    assert all(0.0 <= c <= 1.0 for c in d["confidences"])


def test_ocr_lex_route(server):
    """route=lex must be the SHIPPING path: baseline.read_text + fix_line."""
    import baseline as B
    sys.path.insert(0, str(ROOT / "tools"))
    from lex_projection import fix_line

    img, label = G.generate_one("easy", 4321)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    status, d = _post_json(server + "/api/ocr", {"image": b64, "route": "lex"})
    assert status == 200 and d["route"] == "lex"
    # server-side ground truth, computed in-process on the same image
    want_raw, _ = B.read_text(img, None)
    want = fix_line(want_raw)
    assert d["text"] == want
    if want_raw != want:
        assert d["text_raw"] == want_raw
    else:
        assert "text_raw" not in d
    assert d["family"] == "floor+lex"
    assert d["server_ms"] > 0

    # bad route is a clean 400
    status, d = _post_json(server + "/api/ocr", {"image": b64, "route": "magic"})
    assert status == 400 and d["error"] == "bad-route"


def test_ocr_error_paths(server):
    status, d = _post_json(server + "/api/ocr", {"image": "not-base64!!"})
    assert status == 400 and d["error"] == "bad-payload"
    b64 = base64.b64encode(b"definitely not a png").decode()
    status, d = _post_json(server + "/api/ocr", {"image": b64})
    assert status == 400 and d["error"] == "not-an-image"


def test_ocr_upload_limit(server):
    huge = "A" * (WS.MAX_UPLOAD + 1024)
    data = json.dumps({"image": huge}).encode()
    req = urllib.request.Request(server + "/api/ocr", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            pytest.fail(f"expected 413, got {r.status}")
    except urllib.error.HTTPError as e:
        assert e.code == 413


def test_suites_endpoints(server):
    status, d = _get_json(server + "/api/suites")
    assert status == 200
    s = d["suites"][0]
    assert s["name"] == "suite-x" and s["splits"]["easy"]["total"] == 2
    assert s["splits"]["easy"]["families"] == {"easy": 2}

    status, d = _get_json(server + "/api/suite-items?suite=suite-x&split=easy")
    assert status == 200 and len(d["items"]) == 2
    assert d["items"][0]["id"] == "easy-0000" and d["items"][0]["label"]

    status, body, hdrs = _get(
        server + "/api/suite-image?suite=suite-x&split=easy&id=easy-0000")
    assert status == 200 and body[:4] == b"\x89PNG"
    assert hdrs["Content-Type"] == "image/png"
    assert "X-Item-Label" in hdrs

    # unknown / traversal attempts are 404, not 500
    for q in ("suite=suite-x&split=easy&id=nope",
              "suite=nope&split=easy&id=easy-0000",
              "suite=suite-x&split=easy&id=../../server"):
        status, _ = _get_json(server + "/api/suite-image?" + q)
        assert status == 404


def test_reports_endpoint(server):
    status, d = _get_json(server + "/api/reports")
    assert status == 200 and isinstance(d["reports"], list)
    if d["reports"]:  # repo ships receipts; stay honest if empty
        r = d["reports"][0]
        assert r["file"].endswith(".json") and "run_id" in r
        status, raw = _get_json(server + "/api/report?file=" + r["file"])
        assert status == 200 and ("bench" in raw or "text" in raw)
    status, d = _get_json(server + "/api/report?file=../server.py")
    assert status == 404


def test_bus_endpoint(server):
    status, d = _get_json(server + "/api/bus?channel=general&limit=10")
    assert status == 200 and d["enabled"] is True
    assert d["total"] == 3 and len(d["messages"]) == 3
    assert d["messages"][-1]["from"] == "agent2"
    assert "general" in d["channels"]
    status, d = _get_json(server + "/api/bus?channel=nope")
    assert d["error"] == "channel-not-found" and d["messages"] == []


def test_tasks_endpoint(server):
    status, d = _get_json(server + "/api/tasks")
    assert status == 200 and d["enabled"] is True
    assert d["total"] == 2
    assert d["by_status"] == {"open": 1, "done": 1}
    assert {t["id"] for t in d["tasks"]} == {"t-a", "t-b"}


def test_bus_board_disabled(tmp_path):
    saved = dict(WS.CONFIG)
    WS.CONFIG["bus_dir"] = None
    WS.CONFIG["board_dir"] = None
    try:
        assert WS.read_bus("general", 10)["enabled"] is False
        assert WS.read_tasks()["enabled"] is False
    finally:
        WS.CONFIG.update(saved)


def test_404(server):
    status, d = _get_json(server + "/api/definitely-not-here")
    assert status == 404 and d["error"] == "not-found"
