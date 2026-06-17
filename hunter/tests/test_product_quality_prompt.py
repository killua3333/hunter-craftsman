from hunter.orchestrator.repair import REPAIR_PROMPT, REPAIR_STEP_LIMIT_PROMPT
from hunter.prompts import load_system_prompt


def test_product_quality_in_prompt_rules():
    text = load_system_prompt()
    assert "product_quality" in text
    assert "verified" in text
    assert "task_focused" in text


def test_product_quality_in_repair_prompts():
    assert "product_quality" in REPAIR_PROMPT
    assert "product_quality" in REPAIR_STEP_LIMIT_PROMPT
