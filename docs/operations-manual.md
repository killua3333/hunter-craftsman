# Hunter-Craftsman 日常操作手册

本文面向日常使用和维护人员，尽量不用内部术语。

## 0. 云端共享服务器操作边界

当前云服务器同时运行 Hunter-Craftsman 和其他业务。任何维护操作都必须先确认目录、服务和端口，不能把整台服务器当作本项目的独占环境。

### 本项目范围

截至 2026-08-25，Hunter-Craftsman 的云端范围如下：

| 类型 | 路径或名称 |
| --- | --- |
| 项目根目录 | `/opt/hcapply` |
| Craftsman 代码 | `/opt/hcapply/craftsman` |
| Hunter 代码 | `/opt/hcapply/hunter` |
| Python 虚拟环境 | `/opt/hcapply/.venv` |
| systemd 服务 | `craftsman.service` |
| 服务环境文件 | `/opt/hcapply/craftsman/.env` |
| SQLite 数据库 | `/opt/hcapply/craftsman/craftsman.db` |
| 生成工作区 | `/opt/hcapply/craftsman/workspace` |
| 标准输出日志 | `/var/log/hcapply/output.log` |
| 错误日志 | `/var/log/hcapply/error.log` |
| 本地监听地址 | `127.0.0.1:8791` |
| Nginx 配置 | `/etc/nginx/conf.d/hcapply.conf` |
| 对外域名 | `hcapply.npzsk.com.cn` |

只允许在上述范围内进行本项目的检查和变更。修改 Nginx 前仍需完整核对配置，因为 Nginx 是共享基础服务。

### 不属于本项目的内容

以下内容属于同机其他业务，Hunter-Craftsman 的维护过程中禁止修改、删除、重启或占用其端口：

- `/opt/oral-evaluator`
- `/home/admin/docker-compose.yml`
- `/home/admin/oral-evaluator*`
- Docker 容器 `oral-evaluator`
- 公网端口 `8000`
- Nginx 中与 Hunter-Craftsman 域名无关的站点配置

不要执行整机级 `docker restart`、`docker compose down`、`systemctl restart nginx`、批量杀进程或清理 `/opt`。如确实需要重载 Nginx，应先执行 `sudo nginx -t`，确认变更仅涉及本项目，并取得服务器负责人确认。

### 每次变更前必须检查

```bash
sudo systemctl status craftsman --no-pager
sudo systemctl show craftsman -p WorkingDirectory -p ExecStart -p EnvironmentFiles --no-pager
sudo git -C /opt/hcapply status --short --branch
sudo git -C /opt/hcapply log -5 --oneline --decorate
sudo ss -ltnp | grep -E ':(8791|8000|8800) '
```

检查原则：

- 先记录当前分支、提交号和未提交文件，再决定如何更新。
- 云端存在未提交修改时，不执行覆盖、重置或强制拉取。
- 不直接用本地目录覆盖 `/opt/hcapply`；代码更新必须基于明确分支和提交。
- 当前云端曾部署 `codex/apk-artifact-hotfix`，并存在 `craftsman/.gitignore` 未提交修改。后续操作仍以现场检查结果为准，不能假定分支一直不变。
- 只重启 `craftsman.service`，且仅在本项目代码或环境配置确实变更后执行。
- 修改数据库前必须备份；普通排查优先使用只读查询。

### 凭据与密钥边界

- 不在聊天、截图、日志或文档中展示 `.env`、API Token、Google service account 私钥、keystore 密码。
- 不使用 `cat` 输出完整密钥文件；只检查文件是否存在、JSON 是否可解析、配置项是否为空。
- Dashboard 的访问令牌保存在浏览器本地。服务端已配置 `API_TOKEN` 时，浏览器必须先在“访问设置”中填写同一令牌，否则接口会返回 `401 Unauthorized`。
- service account JSON 能被读取和解析，只说明文件格式正确，不代表它已经获得目标 Play Console App 的权限。
- service account 私钥一旦出现在截图或聊天中，必须在 Google Cloud 删除旧 Key、生成新 Key、替换服务器文件并重启 Craftsman。

### 云端排查纪律

默认只做以下只读操作：查看服务状态、端口、日志、Git 状态、配置项是否存在，以及数据库只读查询。以下操作必须另行确认：修改云端文件、重启服务、修改数据库、验证 Play 包名、创建 Play edit、上传 AAB、提交 internal 版本。

真实发布前还必须确认：

- 页面“验证包名”请求实际到达后端，且目标包名显示 Play 可访问。
- 质量报告为 `release_ready=true` 且质量分不低于 75。
- 任务保留了“生成后自动发布”意图，并创建了 release state 和 release job。
- `PRIVACY_POLICY_URL` 是真实可公网访问的隐私政策地址，不能使用 `https://example.com/privacy`。
- Google Play service account、签名文件、AAB、图标、截图和商店文案均通过发布前检查。

## 1. 启动服务

```powershell
cd D:\A\hunter-craftsman\craftsman
$env:PYTHONPATH="D:\A\hunter-craftsman\hunter\src;D:\A\hunter-craftsman\craftsman"
python .\scripts\serve_dashboard.py
```

只有当前服务器访问 Google Play / Google Publisher API / Tavily 必须经过代理时，才需要设置代理；如果服务器可以直连外网，则无需配置：

```powershell
$env:HTTP_PROXY="http://<your-proxy-host>:<your-proxy-port>"
$env:HTTPS_PROXY="http://<your-proxy-host>:<your-proxy-port>"
```

这里的代理端口仅供服务器本机出网使用，不是对外访问端口。

打开：

```text
http://127.0.0.1:8791/dashboard
```

## 2. 页面怎么用

### 找机会

这里用于发起真实 Google Play 需求发现。

可做的操作：

- 输入或调整搜索方向。
- 选择人工确认或自动进入生成。
- 查看当前阶段：搜索、扫描竞品、抓取评论、分析痛点、生成候选。
- 查看失败原因和下一步处理建议。

### 可做的 App

这里展示真实需求候选。每个候选应包含：

- App 名称
- 细分领域
- 目标用户
- 用户抱怨最多的问题
- 竞品缺口
- 建议先做的功能
- 市场热度、开发适合度、证据强度
- 来源 App 和评论痛点摘要

默认需要人工点击“进入生成”后，系统才开始写 App。

### 生成进度

这里展示已经进入代码生成和发布的任务。

重点看：

- 是否生成成功
- App 质量分
- 是否建议发布
- 失败原因
- 是否已经准备 release
- 是否提交到 internal track

### 技术日志

这里保留 run_id、release_id、原始事件和错误详情，供开发者排查。

## 3. 跑一轮真实流程

1. 启动服务并打开 Dashboard。
2. 在“找机会”页点击开始发现。
3. 等待阶段进度完成。
4. 到“可做的 App”页选择一个候选。
5. 点击进入生成。
6. 到“生成进度”页等待构建和质量检查。
7. 质量达标后再进入发布。
8. 提交到 Google Play internal track 之前，确认包名池、签名、service account 和 Android 构建环境都已准备完成。

### 人工确认与自动发布模式

- `manual`：发现结束后只进入需求池。人工点击“进入生成”后执行 B，但不会自动发布。
- `auto`：证据分、机会分和开发适配分达到门槛时自动进入 B，但不会自动发布。
- `auto_publish`：达到门槛时自动进入 B；B 质量达标且发布配置完整后继续进入 C。
- `auto_publish` 未达到自动选择门槛时会停在需求池。人工确认候选后，系统仍应保留“生成后自动发布”的选择；质量或发布配置不达标时继续阻断，不会绕过门禁。

差评中的“订阅、广告、云同步”等文字表示竞品用户在抱怨的问题，不能直接视为新 App 需要实现的功能或依赖。开发复杂度只根据拟实现功能和明确技术依赖判断。

## 4. Google Play internal track 发布

发布前必须确认：

- Play Console 已经预创建对应包名。
- `PACKAGE_POOL` 中只放已预创建、已授权的包名。
- service account 所属 Google Cloud 项目已启用 `androidpublisher.googleapis.com`。
- service account 有 internal testing 发布权限。
- 签名 keystore 可用。
- Android SDK 或 Docker builder 可用。
- 隐私政策 URL、metadata、图标、截图存在。

当前产品发布只做 Google Play internal 真实上传。

如果配置不完整，系统应阻止发布，并在页面上明确提示是包名池、权限、签名还是素材缺失。

### 哪些配置会长期生效

- Android Publisher API 是 Google Cloud 项目级开关。当前项目启用一次后，新增 App 和包名不需要重复启用；换新 Cloud 项目或 API 被关闭时才需要重新处理。
- service account JSON 和 keystore 可长期复用，但私钥泄露、过期、权限撤销或更换项目时必须替换；keystore 必须备份。
- 公共隐私政策可以供行为一致的本地工具 App 共用。增加联网、登录、广告、分析、支付或云同步后必须更新。
- 每个新 App 仍必须在 Play Console 人工创建，并按权限范围给 service account 授权，再加入包名池。

### internal 之后的人工责任

系统提交 internal 后，App 负责人仍需检查真实功能和商店素材。进入封闭测试或 production 前，还需在 Play Console 人工确认数据安全、内容分级、目标受众、广告、App 访问权限、测试人员、国家地区和发布范围。这些官方声明不能由系统替负责人承担真实性责任。

## 5. 常见问题

### 点击开始发现后失败

先看“找机会”页的阶段进度和“技术日志”。常见原因：

- 本机代理没有设置到服务进程。
- Google Play 搜索请求失败。
- 评论抓取失败或评论数量不足。
- seed query 太窄，搜不到有效竞品。

处理：

- 用代理环境变量重启服务。
- 换更宽的搜索词，例如 checklist、timer、habit tracker、unit converter。
- 保留失败记录，不要用假数据补齐。

### 发现成功但没有进入生成

这是正常行为。默认模式是人工确认，候选会先进入“可做的 App”。只有人工点击进入生成，才会创建生成任务。

### 代码生成失败

常见原因：

- LLM key 缺失或请求失败。
- Android SDK 路径未配置。
- Gradle 构建失败。
- 生成结果没有主界面、交互控件或本地状态，被质量门槛拦截。

处理：

- 检查 `.env` 里的 `DEEPSEEK_API_KEY`。
- 设置 `ANDROID_HOME` 和 `ANDROID_SDK_ROOT`。
- 查看任务质量报告和 build log。
- 必要时选择更聚焦的候选重试。

### 发布失败：包名未创建

Google Play API 不能创建新的 App。需要人工在 Play Console 先创建 App，并把包名加入 `PACKAGE_POOL`。

### 发布失败：权限不足

在 Play Console 的 Users and permissions 中给 service account 授权。至少需要查看 App 信息、管理测试轨道、发布到测试轨道。

处理顺序：

1. 打开 Google Play Console 的“用户和权限”。
2. 使用 service account JSON 中的 `client_email` 查找对应账号；如果不存在，先邀请该账号。
3. 为包名池中的 App 授予查看 App 信息、管理测试轨道和发布测试版本的权限。可使用 Play Console 中等价的 Release manager 权限，但不要授予生产发布权限。
4. 保存后等待权限生效，再回到 Dashboard 点击“验证包名”。
5. 验证成功的包名应显示“Play 可访问”；验证失败时以页面新的错误为准。

验证失败后被标记为 `invalid` 的包名不是永久报废。修复 Play Console 权限后再次执行“验证包名”，系统会重新检查并恢复可用状态。

如果错误为 `play_api_disabled`，不要继续调整 Play Console 的 App 权限。应进入 service account 所属 Google Cloud 项目的“API 和服务 -> API 库”，启用 **Google Play Android Developer API**，等待数分钟后重新验证包名。

如果 service account 私钥曾通过截图、聊天或日志暴露，应先在 Google Cloud 删除旧 Key、生成新 JSON、替换服务器配置文件并重启 Craftsman，然后再验证包名。

## 6. 日常维护建议

- 每次真实上传前检查包名池剩余量。
- 定期归档低质量或重复需求候选。
- 不要把失败任务伪装成成功候选。
- 不要把 demo、fallback、assumption 数据放进客户默认视图。
- 每次大改后至少跑 discovery、quality、release preflight 三类测试。

本地运行发现与发布相关回归测试时，必须同时加入 Hunter 和 Craftsman 源码路径：

```powershell
cd D:\A\hunter-craftsman
$env:PYTHONPATH=".\hunter\src;.\craftsman"
.\craftsman\.venv\Scripts\python.exe -m pytest `
  craftsman\tests\test_real_discovery_api.py `
  craftsman\tests\test_release_async_submit.py `
  craftsman\tests\test_api.py `
  hunter\tests\test_play_monitor_discovery.py `
  -q -p no:cacheprovider
```

## 当前版本补充：质量门槛与包名池

### 生成质量判断

“生成进度”页现在应重点看三个结果：

- 质量分 `>= 75`：建议发布。
- 质量分 `60-74`：可以预览，建议打磨。
- 质量分 `< 60`：需要修复，不应进入发布。

如果页面显示“需要修复”，优先查看扣分原因和下一步建议。常见原因包括主流程弱、UI 空白、无交互、无本地状态、素材缺失、文案过于模板化。

### 包名池操作

“发布配置”页是上架前必须看的页面：

1. 先在 `.env` 配置 `PACKAGE_POOL`。
2. 点击“同步配置”。
3. 点击“验证包名”。
4. 确认可用包名数量大于 0。
5. 无效包名需要在 Play Console 处理后重新验证，或在页面标记无效。

包名池为空或全部无效时，不要尝试真实上传。系统会阻止发布，并提示先处理包名池。

### 给客户的说明口径

可以这样解释：

> Google Play 不允许 API 自动创建全新 App。我们采用更稳定的方式：先在 Play Console 批量创建包名，系统负责自动检查、分配、构建和提交内部测试。

不要说“系统会自动创建 Google Play App”。

## 7. 2026-07-03 实操补充

### 已验证的真实流程

本机已经跑通过一次真实 internal track 发布：

```text
需求：checklist app
App：Checklist App MVP
包名：com.AEM.template002
状态：Google Play internal testing 已发布
versionName：1.0.1
versionCode：3
```

这说明主链路可用：真实发现、生成、质量检查、AAB 构建、Google Play internal track 上传均已完成。

### 同步配置和验证包名的区别

“同步配置”只读取 `.env` 的 `PACKAGE_POOL`，把包名名单写入系统数据库，不访问 Google Play。

“验证包名”会调用 Google Play API，检查这些包名是否已经在 Play Console 创建，以及 service account 是否有权限。

给客户讲法：

```text
同步配置 = 把候选包名导入系统
验证包名 = 检查这些包名是否真的能发布
```

后续更好的产品形态是合并为一个“检查发布配置”按钮，内部自动执行同步和验证。

### 包名池用完怎么办

当前包名池用完后，用户需要在 Play Console 创建新的 App 包名，例如：

```text
AEM Template 003 -> com.AEM.template003
AEM Template 004 -> com.AEM.template004
```

然后：

1. 给 service account 授权这些 App。
2. 确认 `.env PACKAGE_POOL` 已包含这些包名。
3. 在 Dashboard 点击“同步配置”。
4. 点击“验证包名”。
5. 可用包名数量大于 0 后再跑“一键自动生成并上架”。

注意：Google Play API 不能稳定自动创建全新的 Play Console App，因此预创建 App 仍是人工步骤。

### 在哪里看 App 长什么样

Play Console 主要证明发布状态，不是 App 预览器。要看生成 App 的真实内容，优先看：

```text
craftsman/workspace/<run_id>/artifacts/screenshots/
craftsman/workspace/<run_id>/artifacts/app-debug.apk
```

也可以用内部测试账号在 Google Play 安装后查看。

本轮 Checklist App 的截图路径：

```text
craftsman/workspace/4aa416a6-181e-4b10-95c4-c584f03cf485/artifacts/screenshots/
```

### Play Console 里能看到什么

Play Console 的 internal testing 页面能看到版本是否发布，例如“已面向内部测试人员发布”。它不直接展示 App 交互界面。

如果系统日志出现：

```text
commit failed after store asset sync; retrying internal AAB without listing/images
```

表示商店素材同步失败，但系统降级为只上传 AAB。此时 Play Console 能看到测试版本，但名称、描述、截图可能仍是预创建 App 的旧内容。
