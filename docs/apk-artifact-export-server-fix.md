# APK 产物导出 Bug：服务器修复与核验指南

## 1. 适用范围

本指南用于修复以下现象：Android 构建已经生成
`project/app/build/outputs/apk/debug/app-debug.apk`，但任务产物目录
`artifacts/` 中没有 `.apk` 文件，导致用户无法从控制台或仓库约定的产物位置获取 APK。

修复代码位于：

- 分支：`codex/fix-apk-artifact-export`
- 核心修复提交：`70bdcf8 fix(craftsman): export debug APK artifacts`

修复后的行为：

1. Agent B 的 Android debug 构建成功后，自动查找 `app-debug.apk` 或
   `app-universal-debug.apk`。
2. 将 APK 复制到任务目录的 `artifacts/app-debug.apk`。
3. 在任务产物和 `release_bundle.apk_path` 中登记该文件。
4. 如果 Gradle 返回成功却找不到 APK，任务会明确失败，不再产生“构建成功但没有可下载 APK”的假象。

> 修复只影响部署后的新任务。已经执行完毕的历史任务不会自动补齐 APK。

## 2. 修复前准备

### 2.1 安全处理

如果 Android 签名密码、Google Play 服务账号私钥或 API Token 曾出现在截图、聊天记录或日志中，部署前必须先在对应平台轮换这些凭据。

- 不要把真实密码、Token、服务账号 JSON 或 keystore 提交到 Git。
- 服务器上的密钥文件应保存在仓库外或被 `.gitignore` 排除的 secrets 目录中。
- 密钥文件建议仅允许运行服务的账号读取，例如权限设为 `600`。
- 分享日志或截图前，应遮盖 Token、密码、私钥和账号标识。

### 2.2 确认实际部署目录

项目文档的默认仓库目录是 `/opt/hunter-agent`，服务名是 `craftsman`。实际服务器可能使用其他目录，例如 `/opt/hcapply`，不要直接套用默认路径。

先查看正在运行的服务配置：

```bash
sudo systemctl cat craftsman
```

根据输出中的 `WorkingDirectory`、`EnvironmentFile` 和 `ExecStart` 确认：

- `<REPO_ROOT>`：仓库根目录，例如 `/opt/hunter-agent`
- Python 虚拟环境路径，例如 `<REPO_ROOT>/.venv`
- 服务实际读取的环境变量文件

以下命令中的 `<REPO_ROOT>` 和 `<RUN_ID>` 都是占位符，执行前必须替换为服务器真实值。

### 2.3 检查仓库状态

```bash
cd <REPO_ROOT>
git status --short --branch
git branch --show-current
git log -1 --oneline
```

如果 `git status` 显示服务器上有未提交修改，先查明修改来源并备份，不要使用 `git reset --hard` 覆盖服务器配置或他人的改动。

## 3. 部署修复

### 方案 A：直接部署修复分支（推荐先用于验证）

当前修复分支基于 `delivery/2026-07-14`，适合当前同基线服务器直接验证：

```bash
cd <REPO_ROOT>
git fetch origin
git switch codex/fix-apk-artifact-export
git pull --ff-only origin codex/fix-apk-artifact-export
git log --oneline -5
```

确认日志中包含核心修复提交 `70bdcf8`。

### 方案 B：保留服务器的正式发布分支

如果生产服务器必须跟随固定发布分支，应先通过 Pull Request 将修复合入该发布分支，再在服务器执行 `git pull --ff-only`。不要为了这个修复直接把整个 `delivery/2026-07-14` 合并到较旧的 `main`，否则可能同时带入该交付分支上的其他功能变更。

需要临时制作候选发布分支时，可以从当前正式发布分支挑选核心修复提交：

```bash
git switch <RELEASE_BRANCH>
git pull --ff-only origin <RELEASE_BRANCH>
git switch -c codex/apk-artifact-hotfix
git cherry-pick 70bdcf8
```

候选分支通过测试、评审并推送到远端后，再按团队发布流程合并。不要只在生产服务器上保留一个未推送的本地提交。

## 4. 更新运行环境并重启

本次修复没有新增依赖。使用 editable install 的标准部署无需重新安装依赖；如果不确定服务器是否为 editable install，可执行：

```bash
<REPO_ROOT>/.venv/bin/python -m pip install -e <REPO_ROOT>/craftsman
```

随后重启服务：

```bash
sudo systemctl restart craftsman
sudo systemctl status craftsman --no-pager
```

本次没有修改 systemd unit，因此通常不需要执行 `systemctl daemon-reload`。

检查服务健康状态：

```bash
curl -fsS http://127.0.0.1:8791/health
curl -fsS http://127.0.0.1:8791/readyz
```

如启动失败，查看最近日志：

```bash
sudo journalctl -u craftsman -n 100 --no-pager
```

## 5. 创建新任务并核验 APK

### 5.1 确认构建条件

通过服务器的安全配置管理方式确认：

- `SKIP_GRADLE_BUILD=false`
- Android SDK 或 Android Docker 构建环境可用
- 服务账号对 `<REPO_ROOT>/craftsman/workspace` 具有写权限

不要为了排查问题把整个环境变量文件或 secrets 文件打印到终端、日志或聊天中。

可以单独验证工作区权限：

```bash
sudo -u www-data test -w <REPO_ROOT>/craftsman/workspace
```

如果 systemd unit 使用的不是 `www-data`，请替换为 unit 中的 `User`。

### 5.2 触发新构建

登录 `https://hcapply.npzsk.com.cn/`，在“访问设置”中输入服务器配置的 API Token，然后创建一个新的 Android 生成任务。

API Token 是服务端配置的共享访问凭据，前端通过 `X-API-Token` 请求头将其发送给 API。不要把 Token 放入 URL、Git 提交、截图或本指南。未携带 Token 请求受保护的 dashboard API 时返回 `401` 是预期行为，不代表 APK 修复失败。

### 5.3 检查产物

新任务完成后，以该任务的真实 ID 替换 `<RUN_ID>`：

```bash
test -f <REPO_ROOT>/craftsman/workspace/<RUN_ID>/project/app/build/outputs/apk/debug/app-debug.apk
test -f <REPO_ROOT>/craftsman/workspace/<RUN_ID>/artifacts/app-debug.apk
ls -lh <REPO_ROOT>/craftsman/workspace/<RUN_ID>/artifacts/app-debug.apk
```

检查原始 APK 与导出 APK 是否一致：

```bash
sha256sum \
  <REPO_ROOT>/craftsman/workspace/<RUN_ID>/project/app/build/outputs/apk/debug/app-debug.apk \
  <REPO_ROOT>/craftsman/workspace/<RUN_ID>/artifacts/app-debug.apk
```

两个 SHA-256 值应相同。如果项目生成的是 `app-universal-debug.apk`，将第一条路径替换为实际文件路径。

也可以列出最近导出的 APK：

```bash
find <REPO_ROOT>/craftsman/workspace -type f \
  -path '*/artifacts/app-debug.apk' -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' \
  | sort -r | head
```

最终应同时满足：

- Gradle 原始输出目录中存在 debug APK。
- 对应任务的 `artifacts/app-debug.apk` 存在且可读取。
- 两个文件的 SHA-256 一致。
- 控制台任务产物列表中显示 APK，下载功能可用。

## 6. 常见问题排查

### 原始 Gradle 目录也没有 APK

这不是产物导出逻辑的问题，应检查 Gradle、Android SDK、Docker 构建镜像、磁盘空间和项目编译日志。修复代码不会伪造 APK。

### 原始 APK 存在，但新任务的 `artifacts/` 仍没有 APK

依次检查：

1. `git log --oneline -5` 是否包含 `70bdcf8`。
2. `systemctl status craftsman` 显示的进程是否在更新后启动。
3. `systemctl cat craftsman` 中的 `WorkingDirectory` 和 Python 路径是否指向刚更新的仓库。
4. Python 实际导入的包路径是否正确：

```bash
sudo -u www-data <REPO_ROOT>/.venv/bin/python -c 'import craftsman; print(craftsman.__file__)'
```

若服务用户不是 `www-data`，请替换为实际用户。

### 日志显示构建成功但找不到 APK

修复后任务会报告类似 `assembleDebug succeeded but no debug APK output was found` 的错误。这说明 Gradle 命令的退出码为 0，但实际没有在约定目录生成 APK，应继续排查 Gradle 输出路径或构建脚本，而不是忽略错误。

### 只有历史任务缺少 APK

这是预期情况。部署后必须新建任务验证；历史任务不会重新运行，也不会自动从旧项目目录复制产物。

## 7. 回滚

更新前应记录原分支名和提交号。如果修复部署后出现异常，可切回原发布分支并重启：

```bash
cd <REPO_ROOT>
git switch <PREVIOUS_BRANCH>
git pull --ff-only origin <PREVIOUS_BRANCH>
sudo systemctl restart craftsman
sudo systemctl status craftsman --no-pager
```

如果修复已经通过 cherry-pick 合入共享发布分支，应使用 `git revert` 创建可审计的回滚提交并走正常评审流程，不要在共享分支上强制重写历史。

## 8. 验收清单

- [ ] 已轮换曾暴露的 Google Play 服务账号密钥、签名密码和 API Token。
- [ ] 服务器部署代码包含核心修复提交 `70bdcf8`。
- [ ] `craftsman` 服务重启成功，`health` 与 `readyz` 检查通过。
- [ ] 使用 `SKIP_GRADLE_BUILD=false` 创建了一个新任务。
- [ ] 新任务存在 `artifacts/app-debug.apk`。
- [ ] 原始 APK 与导出 APK 的 SHA-256 一致。
- [ ] 控制台能够显示并下载 APK。
- [ ] 日志、截图和 Git 历史中没有新增敏感信息。
