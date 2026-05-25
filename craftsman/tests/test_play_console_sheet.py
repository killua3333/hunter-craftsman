from pathlib import Path

from craftsman.publisher.play_console_sheet import generate_play_console_sheet


def test_play_console_sheet_snapshot(tmp_path):
    handoff = {
        "release_bundle": {"application_id": "com.example.timer"},
        "compliance_metadata": {
            "subtitle": "Timer Pro",
            "description": "A simple timer app for productivity.",
            "keywords": ["timer", "productivity"],
            "privacy_url": "https://timer-privacy.pages.dev/",
        },
    }
    result = generate_play_console_sheet(handoff=handoff, workspace=tmp_path)
    text = result["text"]
    assert "com.example.timer" in text
    assert "Timer Pro" in text
    assert "timer-privacy.pages.dev" in text
    assert "15 分钟" in text
    assert (tmp_path / "play_console_setup.txt").is_file()
    assert result["json"]["package_name"] == "com.example.timer"
