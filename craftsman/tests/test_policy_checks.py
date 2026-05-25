from craftsman.orchestrator.policy_checks import check_release_compliance_metadata


def test_policy_checks_pass_with_complete_metadata():
    result = check_release_compliance_metadata(
        {
            "compliance_metadata": {
                "subtitle": "sub",
                "description": "desc",
                "keywords": ["a"],
                "privacy_url": "https://com-test-publisher.pages.dev/privacy",
            }
        }
    )
    assert result["passed"] is True
    assert result["issues"] == []


def test_policy_checks_fail_on_placeholder_privacy_url():
    result = check_release_compliance_metadata(
        {
            "compliance_metadata": {
                "subtitle": "sub",
                "description": "desc",
                "keywords": ["a"],
                "privacy_url": "https://example.com/privacy",
            }
        }
    )
    assert result["passed"] is False
    assert "compliance_metadata.privacy_url_placeholder" in result["issues"]


def test_policy_checks_fail_when_missing_fields():
    result = check_release_compliance_metadata(
        {
            "compliance_metadata": {
                "subtitle": "",
                "description": "",
                "keywords": [],
                "privacy_url": "invalid-url",
            }
        }
    )
    assert result["passed"] is False
    assert "compliance_metadata.subtitle" in result["issues"]
    assert "compliance_metadata.description" in result["issues"]
    assert "compliance_metadata.keywords" in result["issues"]
    assert "compliance_metadata.privacy_url_format" in result["issues"]
