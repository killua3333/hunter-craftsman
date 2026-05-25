from craftsman.config import settings
from craftsman.orchestrator.alerts import evaluate_run_alerts, reset_alert_state


def test_failure_rate_spike_alert(monkeypatch):
    reset_alert_state()
    monkeypatch.setattr(settings, "alert_window_size", 5)
    monkeypatch.setattr(settings, "alert_min_samples", 3)
    monkeypatch.setattr(settings, "alert_failure_rate_threshold", 0.6)
    monkeypatch.setattr(settings, "alert_timeout_rate_threshold", 0.9)

    # 2/3 failed -> 0.6667 triggers failure spike.
    evaluate_run_alerts(
        run_id="r1",
        opportunity_id="o1",
        revision=1,
        status="failed",
        total_duration_seconds=1.0,
        failure_class="runtime_exception",
    )
    evaluate_run_alerts(
        run_id="r2",
        opportunity_id="o2",
        revision=1,
        status="implementation_complete",
        total_duration_seconds=1.0,
        failure_class=None,
    )
    alerts = evaluate_run_alerts(
        run_id="r3",
        opportunity_id="o3",
        revision=1,
        status="failed",
        total_duration_seconds=1.0,
        failure_class="runtime_exception",
    )
    assert any(a["type"] == "failure_rate_spike" for a in alerts)


def test_timeout_rate_spike_alert(monkeypatch):
    reset_alert_state()
    monkeypatch.setattr(settings, "max_implementation_seconds", 100.0)
    monkeypatch.setattr(settings, "alert_window_size", 4)
    monkeypatch.setattr(settings, "alert_min_samples", 2)
    monkeypatch.setattr(settings, "alert_duration_threshold_ratio", 0.9)
    monkeypatch.setattr(settings, "alert_timeout_rate_threshold", 0.5)
    monkeypatch.setattr(settings, "alert_failure_rate_threshold", 1.1)

    evaluate_run_alerts(
        run_id="t1",
        opportunity_id="o1",
        revision=1,
        status="implementation_complete",
        total_duration_seconds=95.0,
        failure_class=None,
    )
    alerts = evaluate_run_alerts(
        run_id="t2",
        opportunity_id="o2",
        revision=1,
        status="implementation_complete",
        total_duration_seconds=91.0,
        failure_class=None,
    )
    assert any(a["type"] == "timeout_rate_spike" for a in alerts)
