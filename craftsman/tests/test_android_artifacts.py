from pathlib import Path

from craftsman.runtime.android_artifacts import export_debug_apk, find_debug_apk


def test_export_debug_apk_copies_gradle_output_to_artifacts(tmp_path: Path):
    project = tmp_path / "project"
    source = project / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"debug-apk")

    artifacts = tmp_path / "artifacts"
    exported = export_debug_apk(project, artifacts)

    assert find_debug_apk(project) == source
    assert exported == artifacts / "app-debug.apk"
    assert exported.read_bytes() == b"debug-apk"


def test_export_debug_apk_returns_none_when_gradle_output_is_missing(tmp_path: Path):
    artifacts = tmp_path / "artifacts"

    assert export_debug_apk(tmp_path / "project", artifacts) is None
    assert not artifacts.exists()
