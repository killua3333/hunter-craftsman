from craftsman.feedback import build_feedback
from craftsman.models import AgentBStatus
from craftsman.schema_validate import validate_feedback


def test_feedback_schema():
    fb = build_feedback(
        opportunity_id="calc-001",
        revision=1,
        app_name="Calc",
        accepted=False,
        status=AgentBStatus.NEEDS_CLARIFICATION,
        reasons=["core_logic 未说明存储方式"],
        suggested_rules=["core_logic.persistence 必填"],
    )
    data = fb.to_agent_a_dict()
    assert data["agent_b_status"] == "needs_clarification"
    assert validate_feedback(data) == []
