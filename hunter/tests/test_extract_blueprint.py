import json

from hunter.schemas import extract_blueprint_from_text
from tests.conftest import sample_blueprint


def test_extract_from_json_fence():
    bp = sample_blueprint()
    payload = json.dumps(bp.model_dump(), ensure_ascii=False)
    text = f"分析完成。\n\n```json\n{payload}\n```"
    extracted = extract_blueprint_from_text(text)
    assert extracted.app_name == "离线番茄钟"


def test_extract_raw_json_rejected():
    raw = (
        '{"accepted": false, "rejection_reason": "需后端", '
        '"app_name": "", "core_logic": "", "ui_layout": "", "keywords": []}'
    )
    bp = extract_blueprint_from_text(raw)
    assert bp.accepted is False
