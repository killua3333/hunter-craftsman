# Hunter-Craftsman 问题文档逐项答复

## 1. `curl http://127.0.0.1:8791/health` 返回正常，说明什么

这说明当前 `Craftsman` 服务已经启动成功，并且 `127.0.0.1:8791` 这个本机地址可访问。

截图里 `ss -nltp` 也显示 `127.0.0.1:8791` 正在监听，因此可以确认：

- `Craftsman` 服务本身已经启动
- 该端口确实在本机监听
- 不能再把后续问题简单归因成“服务没启动”

## 2. `python -c "import sqlite3; print(sqlite3.sqlite_version)"` 输出 `3.26.0` 是否有问题

`3.26.0` 是当前服务器上 Python 所使用的 SQLite 版本号，本身不是报错。

但它对后续问题有解释作用：当前服务器 SQLite 版本较老，不支持较新的 `RETURNING` SQL 语法，因此会影响部分接口兼容性。

也就是说，这个输出本身不是异常，但它能帮助解释第 3 个问题和第 5 个问题里的 500 报错根因。

## 3. 点击“恢复使用”报错，对程序有什么影响，是否有必要修复

这个问题已经定位清楚，根因是：当前服务器上的 SQLite 版本为 `3.26.0`，而原来的“恢复使用”接口在写审计日志时使用了 `RETURNING id` 语法，老版本 SQLite 不支持该语法，所以会报：

```text
sqlite3.OperationalError: near "RETURNING": syntax error
```

影响范围是局部的：

- “恢复使用”这个按钮会报错
- 该包名无法从当前暂停或无效状态恢复
- 但不会导致整个 Dashboard 或其他接口全部不可用

这个问题建议修复。当前代码已经改为兼容写法，不再依赖 `RETURNING`，因此在更新到最新代码后，应可兼容这类老版本 SQLite 环境。

## 4. 启动后第一次网页访问为什么就处于“排队中”

这通常不是说浏览器一打开就自动新建了一轮任务。

更常见的情况是：

- 数据库中本来就保留了之前未完成或待处理的任务
- Dashboard 启动后会把数据库里的现有任务状态直接读出来

因此，第一次访问页面就看到“排队中”，一般表示系统读到了历史任务状态，而不是页面自动发起了新的流程。

## 5. 运行 `hunter autopilot --publish --timeout 1800 --base-url http://127.0.0.1:8791` 无法启动，并提示“请先启动 craftsman 服务”，怎么理解

- 不是 `Craftsman` 服务没有启动
- 而是 `hunter autopilot --publish` 已经成功请求到了 `Craftsman`
- 随后在调用 `POST /dashboard/api/discovery-runs` 时，后端接口返回了 `500 Internal Server Error`

真正根因是：创建 discovery event 时，数据库层同样使用了老版本 SQLite 不支持的 `RETURNING` 语法，所以报了：

```text
sqlite3.OperationalError: near "RETURNING": syntax error
```

这里还有一个容易混淆的点：

- 截图中的 `GET /dashboard/api/discovery-runs 405 Method Not Allowed` 是正常现象，因为该接口本来就是 `POST` 接口，不支持直接用浏览器 `GET` 打开
- 真正的问题是后面的 `POST /dashboard/api/discovery-runs 500 Internal Server Error`

因此，这个问题不能再表述成“可能是环境没对齐”。从当前截图看，已经可以明确归因为：

- 服务已启动
- 请求已到达后端
- 但 discovery 事件写入时触发了 SQLite 兼容性错误

当前代码已经同步修复了这处兼容问题，更新到最新版本后，应可消除这类 500 报错。

## 6. `Craftsman` 启动 service 应该怎么理解

当前交付版本里，正式常驻服务应以 `Craftsman` 为主。

也就是说，部署时正常需要常驻启动的是：

```bash
python -m craftsman.cli serve --host 127.0.0.1 --port 8791
```

这个服务启动后，会带起后台 Worker，并负责后续的自动流程调度。

## 7. `Hunter` 是否也需要像 `Craftsman` 一样的启动程序

正常不需要单独再做一个必须常驻的 `Hunter` 后台服务。

当前交付版本中：

- `Craftsman` 是常驻主服务
- `Hunter` 的能力会由 `Craftsman` 服务内部去调度

如果运维上为了方便，额外做一个一次性触发的 `hunter.service` 也可以理解，但它不是系统必须依赖的主常驻服务。

## 8. `ExecStart` 应该写哪个命令

如果是部署正式服务，`ExecStart` 建议写 `Craftsman` 服务启动命令，而不是写 `hunter autopilot`。

推荐写法是：

```bash
python -m craftsman.cli serve --host 127.0.0.1 --port 8791
```

`hunter autopilot --base-url ...`、`hunter autopilot --publish --base-url ...`、`hunter autopilot --publish --timeout 1800 --base-url ...` 更适合作为手工触发或脚本触发命令，不建议作为主常驻服务命令。

如果像截图那样配置一个 `Type=oneshot` 的 `hunter.service` 作为触发器，也应理解为“触发任务”，不是“主服务”。

## 9. 超时时间 `timeout` 跟什么有关系

这里的 `timeout` 不是服务启动超时，而是这条自动流程允许等待的总时长。

它通常和以下环节有关：

- Google Play 搜索和评论采集耗时
- 大模型返回耗时
- 代码生成与修复轮数
- Android 构建耗时
- Google Play 上传耗时

例如 `--timeout 1800` 表示这条自动流程最多等待 1800 秒，也就是 30 分钟。

## 10. `User` 和 `Group` 是属于当前用户，还是保持不变

`User` 和 `Group` 应该使用实际部署并运行这套项目的系统用户，不建议机械保持原值不变。

这个用户至少需要具备：

- 对项目目录的读取权限
- 对 `workspace/`、`callbacks/`、`secrets/` 的写入权限
- 如果涉及 Docker 构建，还要有 Docker 调用权限

因此，`User` 和 `Group` 应按当前服务器实际部署账号来配置，而不是简单沿用其他机器上的旧值。

## 11. systemd 下已经能读到 API_TOKEN，Dashboard 为什么仍提示 invalid api token

这不是密钥目录找不到的问题。

从 strace 记录可以看到：

~~~text
openat(..., "secrets/API_TOKEN", O_RDONLY|...) = 12
~~~

返回的文件描述符是正数，表示服务进程已经成功打开并读取了 token 文件。此时浏览器访问 /dashboard 能显示页面也正常，因为它只是静态页面；但页面随后请求 /dashboard/api/overview 等数据接口时，服务会要求请求头中带：

~~~text
X-API-Token: 与服务器 API_TOKEN 完全相同的值
~~~

旧页面没有发送这个请求头，所以会出现 401 invalid api token。这与 systemd 是否能定位 secrets/ 是两件事。

更新到本版本后，页面右上角会出现“访问设置”：

1. 打开 Dashboard。
2. 点击“访问设置”。
3. 输入服务器 API_TOKEN 的实际值。
4. 点击“保存并验证”。

验证成功后，当前浏览器会自动为 Dashboard 的所有数据请求附带 X-API-Token。令牌只保存于该浏览器的本地存储，不会写入仓库、.env 或 URL。

服务器侧只需任选一种方式配置 token，不要两种方式同时配置成不同值：

~~~ini
# /etc/hunter-craftsman/craftsman.env
API_TOKEN=请设置为一段随机且保密的值
~~~

或者：

~~~ini
# /etc/hunter-craftsman/craftsman.env
SECRET_STORE_DIR=/opt/hcapply/craftsman/secrets
~~~

并把 token 内容写入 /opt/hcapply/craftsman/secrets/API_TOKEN。配置变更后执行：

~~~bash
sudo systemctl daemon-reload
sudo systemctl restart craftsman
sudo systemctl status craftsman --no-pager
~~~

注意：如果没有修改 .service 文件，只修改了 craftsman.env 或 token 文件，通常只需要 restart；修改 .service 文件本身后才需要先执行 daemon-reload。