from craftsman.requirement_normalize import normalize_requirement


def test_navigation_view_rewritten():
    req = {
        "features": [{"items": ["使用 NavigationView 展示列表"]}],
        "ui_layout": {"screens": ["sheet 内 NavigationView"]},
    }
    out = normalize_requirement(req)
    assert "NavigationView" not in str(out)
    assert "NavigationStack" in str(out)


def test_platform_defaults_to_android():
    req = {"app": {"name": "A", "bundle_id": "com.demo.app"}}
    out = normalize_requirement(req)
    assert out["platform"]["target"] == "android"
    assert out["app"]["application_id"] == "com.demo.app"
    assert out["app"]["min_android_sdk"] == "24"
