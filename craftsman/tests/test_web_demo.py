import json
from pathlib import Path

from craftsman.tools.web_demo import detect_demo_kind, ensure_windows_demo

SAMPLE = Path(__file__).parent.parent / "examples" / "requirement.sample.json"


def test_detect_calculator():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert detect_demo_kind(req) == "calculator"


def test_detect_timer():
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    req["app"]["name"] = "极简番茄钟"
    assert detect_demo_kind(req) == "timer"


def test_ensure_windows_demo_writes_index(tmp_path):
    req = json.loads(SAMPLE.read_text(encoding="utf-8"))
    ws = tmp_path / "ws"
    ws.mkdir()
    out = ensure_windows_demo(ws, req)
    assert out == ws / "index.html"
    html = out.read_text(encoding="utf-8")
    assert "<script" in html.lower()
    assert "简易计算器" in html
