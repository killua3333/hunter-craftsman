from unittest.mock import patch

from hunter.orchestrator.pipeline import _feedback_learning
from hunter.schemas.opportunity import (
    AppOpportunityBlueprint,
    BlueprintApp,
    BlueprintBranding,
    BlueprintBudget,
    BlueprintCoreLogic,
    BlueprintFeature,
    BlueprintRequirement,
    BlueprintStore,
    BlueprintUiLayout,
    EvidenceItem,
)


def sample_blueprint() -> AppOpportunityBlueprint:
    requirement = BlueprintRequirement(
        app=BlueprintApp(name="离线番茄钟", bundle_id="com.hunter.pomodoro"),
        features=[
            BlueprintFeature(
                id="home",
                type="list",
                title="专注",
                items=["25分钟", "5分钟休息", "历史"],
            )
        ],
        core_logic=BlueprintCoreLogic(
            persistence="UserDefaults",
            description="本地倒计时与历史记录，无网络。",
        ),
        ui_layout=BlueprintUiLayout(
            navigation="stack",
            screens=["顶部计时器", "底部开始/暂停"],
        ),
        branding=BlueprintBranding(primary_color="#FF6B35", icon_text="番"),
        store=BlueprintStore(
            subtitle="学生专注计时",
            description="本地番茄钟，离线可用。",
            keywords=["番茄钟", "专注", "计时"],
            privacy_url="https://example.com/privacy",
        ),
        budget=BlueprintBudget(max_features=8, max_hours=2.0),
    )
    return AppOpportunityBlueprint(
        accepted=True,
        app_name="离线番茄钟",
        core_logic="本地倒计时与历史，UserDefaults 存储。",
        ui_layout="stack：计时器 + 开始按钮",
        keywords=["番茄钟", "专注", "计时"],
        data_quality="assumption",
        evidence=[
            EvidenceItem(
                query="学生 番茄钟 app 痛点",
                source="assumption://未调研时的合理推断",
                snippet="学生群体需要无广告、离线的专注计时工具",
            )
        ],
        requirement=requirement,
    )


def test_orchestrator_clarify_then_implement():
    blueprint = sample_blueprint()
    needs_clarification = {
        "agent_b_status": "needs_clarification",
        "opportunity_id": "focus-001",
        "revision": 1,
        "reasons": ["ui_layout.screens 过简"],
        "suggested_rules": ["补充 screens"],
        "blueprint": {"open_questions": ["是否单屏？"]},
    }
    accepted = {"agent_b_status": "accepted", "opportunity_id": "focus-001", "revision": 2}
    implemented = {
        "agent_b_status": "implementation_complete",
        "opportunity_id": "focus-001",
        "revision": 2,
        "reasons": [],
    }

    session_results = [
        {"blueprint": blueprint, "answer": "{}"},
        {"blueprint": blueprint, "answer": "{}"},
    ]

    class FakeSession:
        def __init__(self):
            self._i = 0

        def send(self, _msg):
            out = session_results[min(self._i, len(session_results) - 1)]
            self._i += 1
            return out

    with (
        patch("hunter.orchestrator.pipeline.SpecialistSession", FakeSession),
        patch(
            "hunter.orchestrator.pipeline.run_analyze",
            side_effect=[needs_clarification, accepted],
        ),
        patch(
            "hunter.orchestrator.pipeline.start_implementation",
            return_value={"run_id": "run-1", "agent_b_status": "in_progress"},
        ),
        patch(
            "hunter.orchestrator.pipeline.wait_for_run_completion",
            return_value=implemented,
        ),
        patch("hunter.orchestrator.pipeline.save_feedback_raw"),
    ):
        from hunter.orchestrator import run_opportunity_pipeline

        outcome = run_opportunity_pipeline(
            "做一个番茄钟",
            opportunity_id="focus-001",
            save_feedback=False,
        )

    assert outcome["rounds"] == 2
    assert outcome["revision"] == 2
    assert outcome["feedback"]["agent_b_status"] == "implementation_complete"


def test_run_blueprint_pipeline_from_chat_blueprint():
    blueprint = sample_blueprint()
    implemented = {
        "agent_b_status": "implementation_complete",
        "opportunity_id": "focus-001",
        "revision": 1,
        "reasons": [],
    }
    session_results = [{"blueprint": blueprint, "answer": "{}"}]

    class FakeSession:
        def __init__(self):
            self._i = 0

        def send(self, _msg):
            out = session_results[min(self._i, len(session_results) - 1)]
            self._i += 1
            return out

    with (
        patch("hunter.orchestrator.pipeline.SpecialistSession", FakeSession),
        patch(
            "hunter.orchestrator.pipeline.run_analyze",
            return_value={"agent_b_status": "accepted", "opportunity_id": "focus-001", "revision": 1},
        ),
        patch(
            "hunter.orchestrator.pipeline.start_implementation",
            return_value={"run_id": "run-2", "agent_b_status": "in_progress"},
        ),
        patch(
            "hunter.orchestrator.pipeline.wait_for_run_completion",
            return_value=implemented,
        ),
        patch("hunter.orchestrator.pipeline.save_feedback_raw"),
    ):
        from hunter.orchestrator import run_blueprint_pipeline

        outcome = run_blueprint_pipeline(
            blueprint,
            opportunity_id="focus-001",
            save_feedback=False,
        )

    assert outcome["rounds"] == 1
    assert outcome["feedback"]["agent_b_status"] == "implementation_complete"


def test_run_autopilot_pipeline():
    blueprint = sample_blueprint()
    implemented = {
        "agent_b_status": "implementation_complete",
        "opportunity_id": "auto-001",
        "revision": 1,
        "reasons": [],
    }
    session_results = [{"blueprint": blueprint, "answer": '{"accepted": true}' }]

    class FakeDiscoverySession:
        def __init__(self):
            self._i = 0

        def send(self, _msg):
            out = session_results[min(self._i, len(session_results) - 1)]
            self._i += 1
            return out

    with (
        patch("hunter.agents.specialist.DiscoverySession", FakeDiscoverySession),
        patch(
            "hunter.orchestrator.pipeline.run_analyze",
            return_value={"agent_b_status": "accepted", "opportunity_id": "auto-001", "revision": 1},
        ),
        patch(
            "hunter.orchestrator.pipeline.start_implementation",
            return_value={"run_id": "run-auto", "agent_b_status": "in_progress"},
        ),
        patch(
            "hunter.orchestrator.pipeline.wait_for_run_completion",
            return_value=implemented,
        ),
        patch("hunter.orchestrator.pipeline.save_feedback_raw"),
    ):
        from hunter.orchestrator import run_autopilot_pipeline

        outcome = run_autopilot_pipeline(save_feedback=False)

    assert outcome["mode"] == "autopilot"
    assert outcome["accepted"]
    assert outcome["feedback"]["agent_b_status"] == "implementation_complete"


def test_feedback_learning_includes_quality_summary():
    text = _feedback_learning(
        {
            "agent_b_status": "implementation_complete",
            "artifacts": {
                "quality": {
                    "summary": "demo-level artifact with reduced native validation",
                    "risks": ["demo_only_output", "native_verification_skipped_or_unavailable"],
                }
            },
            "reasons": ["quality_risks: demo_only_output"],
        },
        prefix="implementation",
    )
    assert "quality:" in text
    assert "demo_only_output" in text


def test_clarification_prompt_includes_quality_summary():
    from hunter.orchestrator.pipeline import _build_clarification_prompt

    prompt = _build_clarification_prompt(
        {
            "reasons": ["demo only"],
            "suggested_rules": ["prefer verified builds"],
            "blueprint": {"open_questions": ["Need richer native validation?"]},
            "artifacts": {
                "quality": {
                    "summary": "demo-level artifact with reduced native validation",
                    "risks": ["demo_only_output"],
                }
            },
        },
        2,
    )
    assert "quality_summary" in prompt
    assert "demo-level artifact" in prompt
