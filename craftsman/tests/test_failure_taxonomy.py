from craftsman.orchestrator.failure_taxonomy import classify_build_failure, classify_runtime_exception


def test_classify_build_failure_missing_symbol():
    result = classify_build_failure(["use of unresolved identifier 'Foo'"])
    assert result["category"] == "missing_symbol"
    assert result["retryable"] is False
    assert result["suggested_rules"]


def test_classify_build_failure_timeout_retryable():
    result = classify_build_failure(["build timed out after 120s"])
    assert result["category"] == "build_timeout"
    assert result["retryable"] is True


def test_classify_runtime_exception_transient():
    result = classify_runtime_exception(RuntimeError("database is locked"))
    assert result["category"] == "transient_infra"
    assert result["retryable"] is True
