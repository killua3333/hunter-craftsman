from pathlib import Path


def test_deploy_assets_exist():
    root = Path(__file__).resolve().parents[2]
    expected = [
        root / "docker" / "deploy-craftsman.sh",
        root / "docker" / "preflight-check.sh",
        root / "docker" / "bootstrap-ubuntu.sh",
        root / "docker" / "smoke-check.sh",
        root / "docker" / "smoke-check.ps1",
        root / "docker" / "systemd" / "hunter-autopilot.service",
        root / "docker" / "systemd" / "hunter-autopilot.timer",
        root / "docker" / "systemd" / "hunter.env.example",
        root / "docker" / "systemd" / "install-hunter-autopilot.sh",
        root / "docker" / "nginx" / "install-craftsman-nginx.sh",
    ]
    for path in expected:
        assert path.is_file()
