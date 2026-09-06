from craftsman.tools.android_smoke import parse_smoke_crash, run_android_smoke
from craftsman.config import settings


def test_parse_smoke_crash():
    log = "E AndroidRuntime: FATAL EXCEPTION: main\nE AndroidRuntime: java.lang.NullPointerException"
    parsed = parse_smoke_crash(log)
    assert len(parsed["errors"]) >= 1


def test_run_android_smoke_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "android_smoke_test", "off")
    result = run_android_smoke(tmp_path, "com.test.app")
    assert result.skipped is True
    assert result.ok is True


def test_run_android_smoke_skipped_no_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "android_smoke_test", "auto")
    monkeypatch.setattr("craftsman.tools.android_smoke.is_docker_available", lambda: False)
    result = run_android_smoke(tmp_path, "com.test.app")
    assert result.skipped is True


def test_run_android_smoke_returns_real_device_screenshots(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "android_smoke_test", "force")
    report_dir = tmp_path / "app" / "build" / "reports" / "device-acceptance"
    report_dir.mkdir(parents=True)
    shot = report_dir / "after-interaction.png"
    shot.write_bytes(b"png")
    monkeypatch.setattr(
        "craftsman.tools.android_smoke.run_smoke_in_container",
        lambda project_dir, package_id: type(
            "Result", (), {"ok": True, "reasons": [], "log": "[smoke] passed"}
        )(),
    )

    result = run_android_smoke(tmp_path, "com.test.app")

    assert result.ok is True
    assert result.skipped is False
    assert result.screenshot_paths == [str(shot)]
