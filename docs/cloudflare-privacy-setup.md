# Cloudflare Pages 隐私政策部署

Agent B 在实现完成后，若 `store.privacy_url` 仍为占位符（`example.com`），会自动生成 HTML 并部署到 Cloudflare Pages。

## 前置条件

1. [Cloudflare 账号](https://dash.cloudflare.com/)
2. **Account ID**：Dashboard → 右侧栏 **Account ID**
3. **API Token**：My Profile → API Tokens → Create Token  
   - 模板：**Edit Cloudflare Workers** 或自定义 Pages 编辑权限  
   - 权限：`Account` → `Cloudflare Pages` → `Edit`

## 环境变量

在 [`craftsman/.env`](../craftsman/.env) 配置：

```env
PRIVACY_DEPLOY_DRY_RUN=false
PRIVACY_CONTACT_EMAIL=you@example.com
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
```

Live 部署走 Wrangler 同款 Direct Upload v2 流程：`upload-token` → `check-missing` → `assets/upload` → `deployments`（`manifest` 字段映射 `/index.html` → blake3 hash）。需 `pip install -e ".[publish]"`（含 `blake3`）。

Dry-run（默认 `true`）仅生成本地 `workspace/{run_id}/privacy/index.html`，URL 写入 `{slug}-privacy.pages.dev` 格式但不调用 API。

## 项目命名

- Slug：`{bundle_id 末段}-privacy`（例如 `com.brand.timer` → `timer-privacy`）
- 公开 URL：`https://timer-privacy.pages.dev/`

## 验收

1. 跑完 Agent B 后 `store.privacy_url` 为 `*.pages.dev`
2. 浏览器可打开该 URL
3. Play Console 隐私政策字段可填同一 URL

## 故障排查

| 现象 | 处理 |
|------|------|
| `privacy_deploy_failed: missing CLOUDFLARE_*` | 检查 token / account id |
| `CF project create failed` | Token 权限不足或项目名冲突 |
| 仍显示 example.com | 确认 `PRIVACY_DEPLOY_DRY_RUN=false` |

详见 [`craftsman/craftsman/publisher/privacy_policy.py`](../craftsman/craftsman/publisher/privacy_policy.py)。
