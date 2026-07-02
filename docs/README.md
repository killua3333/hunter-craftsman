# Hunter-Craftsman 文档索引

建议接手方按下面顺序阅读。

## 第一组：交接必读

- [handoff.md](handoff.md)：项目现状、真实能力、启动方式、配置边界、已知问题。
- [operations-manual.md](operations-manual.md)：日常操作手册，从启动服务到处理失败。
- [play-console-setup-checklist.md](play-console-setup-checklist.md)：Google Play internal track 所需账号、包名池、签名和 service account 配置。
- [demo-script.md](demo-script.md)：给客户或内部评审演示时的推荐脚本。

## 第二组：产品与前端

- [product-roadmap.md](product-roadmap.md)：产品路线图和阶段目标。
- [frontend-product-spec.md](frontend-product-spec.md)：用户工作台的信息架构、字段和交互说明。
- [client-overview.md](client-overview.md)：非技术视角的项目介绍。

## 第三组：三段智能体

- [agent-a-demand-discovery.md](agent-a-demand-discovery.md)：Google Play 需求发现、证据和评分逻辑。
- [agent-b-code-quality.md](agent-b-code-quality.md)：App 生成、质量报告、发布门槛和修复策略。
- [agent-c-internal-testing.md](agent-c-internal-testing.md)：internal track 发布状态、失败分类和操作原则。
- [agent-c-architecture.md](agent-c-architecture.md)：Agent C 更详细的架构说明。

## 第四组：运维与扩展

- [windows-scheduler-guide.md](windows-scheduler-guide.md)：Windows 自动调度。
- [docker-android-ci.md](docker-android-ci.md)：Android Docker 构建环境。
- [cloudflare-privacy-setup.md](cloudflare-privacy-setup.md)：隐私政策页面部署。
- [secret-management-plan.md](secret-management-plan.md)：密钥管理方案。
- [execution-runtime-ops.md](execution-runtime-ops.md)：执行运行时和 worker 运维。

## 当前阶段判断

项目已经具备“真实 Play 需求发现 -> 人工选择 -> App 生成 -> internal track 发布尝试”的主链路，但仍需要继续打磨：

- Agent B 生成质量需要持续提高，避免“能编译但不像真实产品”。
- 包名池必须和 Play Console 预创建 App 严格对齐。
- 用户前端应继续减少技术术语，只在技术日志中保留 run_id、release_id 和原始事件。