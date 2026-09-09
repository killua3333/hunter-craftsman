# 移动端后台接口要求

本文件定义“ai帮我赚钱”移动端与供应商固定后台之间的接口契约。移动端用户只粘贴自己的 DeepSeek API Key，不填写服务器地址，也不直接访问 DeepSeek。

## 固定后台地址

构建安装包时设置：

```bash
VITE_BACKEND_URL=https://api.example.com npm run cap:sync
```

正式环境必须使用受信任证书的 HTTPS 地址。未设置时仅为 Android 模拟器开发地址 `http://10.0.2.2:8791`，不得用于客户发布包。

## 认证流程

### `POST /mobile/api/session`

接收并验证用户的 DeepSeek API Key，验证成功后返回供应商后台的短期会话 Token。

请求：

```json
{
  "provider": "deepseek",
  "api_key": "<用户提交的密钥>"
}
```

成功响应：

```json
{
  "access_token": "<短期不透明会话令牌>",
  "expires_in": 3600
}
```

错误响应使用 HTTP `400`、`401`、`429` 或 `503`，并返回：

```json
{
  "detail": "可安全展示给用户的错误说明"
}
```

后台必须实际调用 DeepSeek 的轻量接口验证密钥。不得把 DeepSeek Key 返回给客户端、写入日志、错误追踪、分析事件或任务输出。若需要跨任务保存，必须使用 KMS/密钥管理服务加密，并支持删除和轮换。

后续请求统一携带：

```http
X-API-Token: <access_token>
```

会话 Token 必须绑定单一客户空间，过期、撤销或额度不足时返回 `401` 或 `403`。

## 必需接口

### `GET /health`

验证会话和服务可用性。返回 `2xx` JSON。

### `GET /dashboard/api/overview`

返回当前客户的总览数据：

```json
{
  "summary": {
    "earnings": {
      "total_earnings_estimated": 0,
      "app_count": 0
    }
  },
  "opportunities": [],
  "pipeline": [],
  "releases": []
}
```

所有数组和汇总必须限定为当前会话所属客户，禁止跨客户读取。

### `POST /dashboard/api/discovery-runs`

请求字段：`seed_queries`、`categories`、`mode`、`operator`。返回至少包含 `run_id`。

### `GET /dashboard/api/discovery-runs/{run_id}`

返回 `status`、`progress`、`message` 或 `current_step`。终态为 `completed` 或 `failed`。只能查询当前客户创建的任务。

### `POST /dashboard/api/opportunities/{candidate_id}/implement`

请求字段：`operator`、`auto_release`。后台先验证机会归属和账户额度，再创建 Agent B 任务并返回 `run_id`。

## 生产与计费要求

- 任务创建前检查余额或制作额度，并采用“冻结 → 成功扣除 / 失败退回”的账本流程。
- Agent A、B、C 的数据库记录、工作目录、构建产物和日志必须按客户隔离。
- 质量分低于 75 或设备验收未通过时，不得生成可交付安装包。
- 发布接口当前只允许内部发布；接入应用商店前必须增加客户授权和独立签名管理。
- 对会话创建、发现、制作和轮询接口设置速率限制与幂等控制。
- 日志只能记录密钥指纹或末四位，不能记录完整 DeepSeek Key、会话 Token或请求头。

## 建议后续接口

- `DELETE /mobile/api/provider-key`：删除保存的 DeepSeek Key并撤销相关会话。
- `POST /mobile/api/session/refresh`：刷新短期会话。
- `GET /mobile/api/balance`：读取余额、冻结金额和可用制作次数。
- `GET /mobile/api/artifacts/{run_id}`：列出当前客户可下载的产物。
- `POST /mobile/api/artifacts/{artifact_id}/download-ticket`：签发短时下载地址。
- 注册、登录、充值订单和支付回调接口：用于正式多客户收费版本。

## 上线验收

- 使用正式 HTTPS 域名重新构建 APK。
- 验证无效 Key、过期 Key、额度不足和服务不可用的错误提示。
- 检查数据库、日志、崩溃报告和代理日志均不含完整密钥。
- 用两个测试客户验证机会、任务、收益和产物完全隔离。
- 对密钥删除、会话撤销、任务失败退款和重复请求执行自动化测试。
