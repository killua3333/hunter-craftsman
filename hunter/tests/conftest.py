"""测试用完整 Blueprint 夹具。"""

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


def sample_blueprint(**overrides) -> AppOpportunityBlueprint:
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
    data = {
        "accepted": True,
        "rejection_reason": None,
        "app_name": "离线番茄钟",
        "core_logic": "本地倒计时与历史，UserDefaults 存储。",
        "ui_layout": "stack：计时器 + 开始按钮",
        "keywords": ["番茄钟", "专注", "计时"],
        "data_quality": "assumption",
        "evidence": [
            EvidenceItem(
                query="学生 番茄钟 app 痛点",
                source="assumption://未调用搜索时的合理推断",
                snippet="学生群体需要无广告、离线的专注计时工具",
            )
        ],
        "requirement": requirement,
    }
    data.update(overrides)
    return AppOpportunityBlueprint(**data)
