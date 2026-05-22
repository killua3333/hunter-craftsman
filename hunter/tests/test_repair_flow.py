from unittest.mock import MagicMock

from hunter.orchestrator.repair import ensure_blueprint
from tests.conftest import sample_blueprint


def test_ensure_blueprint_repairs_on_second_turn():
    good = sample_blueprint()
    bad_result = {"blueprint": None, "parse_error": "JSON 校验失败:\n  - requirement.features: …", "answer": "bad"}
    good_result = {
        "blueprint": good,
        "parse_error": None,
        "answer": "{}",
    }

    session = MagicMock()
    session.send.side_effect = [bad_result, good_result]

    bp, _ = ensure_blueprint(session, "做一个番茄钟", max_attempts=3)
    assert bp.accepted is True
    assert session.send.call_count == 2
