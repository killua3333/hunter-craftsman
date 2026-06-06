from unittest.mock import MagicMock

from hunter.orchestrator.repair import REPAIR_STEP_LIMIT_PROMPT, _repair_message, ensure_blueprint
from tests.conftest import sample_blueprint


def test_repair_message_step_limit():
    msg = _repair_message("parse fail", "Sorry, need more steps to process this request.")
    assert msg == REPAIR_STEP_LIMIT_PROMPT


def test_ensure_blueprint_recovers_after_step_limit():
    good = sample_blueprint()
    limit_result = {
        "blueprint": None,
        "parse_error": "LangGraph 步数用尽",
        "answer": "Sorry, need more steps to process this request.",
    }
    good_result = {"blueprint": good, "parse_error": None, "answer": "{}"}
    session = MagicMock()
    session.send.side_effect = [limit_result, good_result]

    bp, _ = ensure_blueprint(session, "autopilot", max_attempts=3)
    assert bp.accepted is True
    assert session.send.call_args_list[1][0][0] == REPAIR_STEP_LIMIT_PROMPT
