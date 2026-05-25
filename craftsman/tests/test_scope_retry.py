from craftsman.requirement_normalize import shrink_requirement_scope


def test_shrink_requirement_scope():
    req = {
        "app": {"name": "Demo", "bundle_id": "com.demo.app"},
        "features": [
            {"id": "a", "type": "list", "title": "A", "items": ["1", "2", "3"]},
            {"id": "b", "type": "list", "title": "B", "items": ["x"]},
        ],
        "core_logic": {"persistence": "SharedPreferences", "description": "x"},
    }
    shrunk = shrink_requirement_scope(req)
    assert len(shrunk["features"]) == 1
    assert len(shrunk["features"][0]["items"]) <= 2
    assert shrunk["core_logic"]["persistence"] == "none"
    assert shrunk.get("_scope_retry") is True
