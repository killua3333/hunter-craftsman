from pathlib import Path


def test_preflight_script_exists():
    root = Path(__file__).resolve().parents[2]
    script = root / "docker" / "preflight-check.ps1"
    assert script.is_file()
