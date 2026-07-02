# Agent C 内部测试发布策略

Agent C 第一阶段只稳定 Google Play `internal` 内部测试轨道，不自动推 production。

## 发布前检查

release handoff、包名、隐私政策 URL、商店元数据、签名配置、AAB 构建和 Play service account 都必须可用。

## 状态

核心状态包括：prepared、approved、submitting、building_aab、uploading_internal、internal_submitted、dry_run_complete、failed、needs_manual_action。

## 失败分类

常见分类：package_not_precreated、service_account_permission、version_code_conflict、signing_config、metadata_incomplete、play_api_transient、internal_track_unavailable。

## 操作原则

Dry-run 成功只表示链路演练通过；真实上传成功后状态为 internal_submitted。production 发布和商业实验另行规划。
