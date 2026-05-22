from craftsman.requirement_normalize import normalize_requirement


def test_navigation_view_rewritten():
    req = {
        "features": [{"items": ["使用 NavigationView 展示列表"]}],
        "ui_layout": {"screens": ["sheet 内 NavigationView"]},
    }
    out = normalize_requirement(req)
    assert "NavigationView" not in str(out)
    assert "NavigationStack" in str(out)
