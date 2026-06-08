import argparse
import sys

import pytest

from hunter import main as main_mod


def _run_parser_defaults() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser


def test_run_timeout_default_is_600():
    args = _run_parser_defaults().parse_args([])
    assert args.timeout == 600.0


def test_autopilot_timeout_floor():
    assert max(600.0, 1800.0) == 1800.0
    assert max(2400.0, 1800.0) == 2400.0


def test_run_autopilot_passes_minimum_1800_to_cmd(monkeypatch):
    captured: dict[str, float] = {}

    def fake_autopilot(**kwargs):
        captured["timeout"] = float(kwargs["timeout"])
        return 0

    monkeypatch.setattr(main_mod, "cmd_autopilot", fake_autopilot)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hunter", "run", "离线番茄钟", "--autopilot", "--timeout", "600"],
    )
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 0
    assert captured["timeout"] == 1800.0


def test_autopilot_focus_flags_are_passed_to_cmd(monkeypatch):
    captured: dict[str, object] = {}

    def fake_autopilot(**kwargs):
        captured["product_focus"] = kwargs["product_focus"]
        return 0

    monkeypatch.setattr(main_mod, "cmd_autopilot", fake_autopilot)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hunter",
            "autopilot",
            "--region",
            "东南亚",
            "--audience",
            "大学生",
            "--scenario",
            "通勤碎片时间",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 0
    assert captured["product_focus"].model_dump(exclude_none=True) == {
        "region": "东南亚",
        "audience": "大学生",
        "scenario": "通勤碎片时间",
    }
