import pytest

from hunter.config import validate_model_for_agent


def test_validate_rejects_reasoner():
    with pytest.raises(ValueError, match="deepseek-chat"):
        validate_model_for_agent("deepseek-v4-pro")


def test_validate_accepts_chat():
    validate_model_for_agent("deepseek-chat")
