from craftsman.orchestrator.device_acceptance import (
    build_android_device_acceptance_report,
    write_device_acceptance_report,
)


def test_device_acceptance_distinguishes_launch_from_core_flow(tmp_path):
    project = tmp_path / "project"
    screenshots = project / "app" / "build" / "reports" / "device-acceptance"
    screenshots.mkdir(parents=True)
    (screenshots / "after-interaction.png").write_bytes(b"png")

    report = build_android_device_acceptance_report(
        project_dir=project,
        build_verified=True,
        smoke_ok=True,
        smoke_skipped=False,
        smoke_reason="",
        acceptance_actions=["Create an item", "Item remains after restart"],
    )

    assert report["status"] == "launch_verified"
    assert report["launch_verified"] is True
    assert report["random_smoke_verified"] is True
    assert report["core_flow_verified"] is False
    assert report["persistence_verified"] is False
    assert report["screenshot_source"] == "android_emulator"


def test_device_acceptance_records_unavailable_environment(tmp_path):
    report = build_android_device_acceptance_report(
        project_dir=tmp_path,
        build_verified=True,
        smoke_ok=True,
        smoke_skipped=True,
        smoke_reason="docker not available",
        acceptance_actions=[],
    )

    assert report["status"] == "unavailable"
    assert report["launch_verified"] is False
    path = write_device_acceptance_report(tmp_path, report)
    assert path.is_file()
