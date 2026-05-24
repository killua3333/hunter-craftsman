from craftsman.tools.gradle_errors import parse_gradle_errors


def test_parse_gradle_kotlin_errors():
    log = """
e: file:///D:/proj/app/src/main/java/com/craftsman/MainActivity.kt:10:5 Unresolved reference: foo
FAILURE: Build failed with an exception.
"""
    parsed = parse_gradle_errors(log)
    assert parsed["error_count"] >= 1
    assert parsed["errors"][0]["category"] == "undefined_symbol"
