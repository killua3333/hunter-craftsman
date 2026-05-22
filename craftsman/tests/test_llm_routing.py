from unittest.mock import patch

from craftsman import llm


def test_analyze_requirement_uses_chat_model():
    with patch.object(llm, "_chat_json", return_value={"reasons": [], "suggested_rules": [], "open_questions": []}) as mock:
        llm.analyze_requirement_llm({"app": {"name": "T"}})
        assert mock.call_args.kwargs["model"] == llm.settings.deepseek_chat_model


def test_generate_code_uses_pro_model():
    payload = {
        "files": [
            {"path": "Sources/App.swift", "content": "@main struct XApp: App { var body: some Scene { WindowGroup { ContentView() } } }"},
            {"path": "Sources/ContentView.swift", "content": "struct ContentView: View { var body: some View { Text(\"Hi\") } }"},
            {"path": "Sources/Color+Hex.swift", "content": "import SwiftUI\nextension Color { static let brandPrimary = Color.blue }"},
        ]
    }
    with patch.object(llm, "_chat_json", return_value=payload) as mock:
        files = llm.generate_code_llm({"app": {"name": "T"}})
        assert mock.call_args.kwargs["model"] == llm.settings.deepseek_pro_model
        assert "Sources/App.swift" in files


def test_fix_code_uses_pro_model():
    with patch.object(llm, "_chat_json", return_value={"files": [{"path": "Sources/App.swift", "content": "x"}]}) as mock:
        llm.fix_code_llm({}, {"Sources/App.swift": "old"}, [{"message": "error"}], 1)
        assert mock.call_args.kwargs["model"] == llm.settings.deepseek_pro_model
