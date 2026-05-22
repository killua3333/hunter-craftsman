from hunter.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
    append_tool_result,
    build_conversation,
)


def test_build_conversation():
    msgs = build_conversation("你是助手", "你好")
    assert len(msgs) == 2
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], HumanMessage)


def test_append_tool_result():
    msgs = build_conversation("sys", "hi")
    extended = append_tool_result(
        msgs,
        tool_call_id="call_1",
        content='{"ok": true}',
        tool_name="echo",
    )
    assert len(extended) == 3
    assert isinstance(extended[-1], ToolMessage)
    assert extended[-1].tool_call_id == "call_1"
