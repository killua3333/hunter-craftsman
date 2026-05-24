"""隐私政策生成 + Cloudflare Pages 部署。"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from craftsman.config import settings
from craftsman.secrets import resolve_secret_value

_PLACEHOLDER_MARKERS = ("example.com", "placeholder", "http://localhost")
_CF_API = "https://api.cloudflare.com/client/v4"


def is_placeholder_privacy_url(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u:
        return True
    return any(m in u for m in _PLACEHOLDER_MARKERS)


def _slug_from_bundle(bundle_id: str) -> str:
    tail = bundle_id.split(".")[-1] if bundle_id else "app"
    slug = re.sub(r"[^a-z0-9-]", "-", tail.lower()).strip("-")
    return f"{slug or 'app'}-privacy"


def render_privacy_html(req: dict[str, Any]) -> str:
    app = req.get("app") or {}
    store = req.get("store") or {}
    core = req.get("core_logic") or {}
    name = str(app.get("name") or "App")
    bundle = str(app.get("bundle_id") or "com.example.app")
    persistence = str(core.get("persistence") or "none")
    email = settings.privacy_contact_email
    features = req.get("features") or []
    feat_lines = []
    for f in features[:5]:
        if isinstance(f, dict):
            feat_lines.append(str(f.get("title") or f.get("id") or ""))
    feat_text = "、".join(x for x in feat_lines if x) or "基础工具功能"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{name} 隐私政策</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }}
    h1 {{ font-size: 1.5rem; }}
  </style>
</head>
<body>
  <h1>{name} 隐私政策</h1>
  <p>最后更新：自动生成</p>
  <h2>概述</h2>
  <p>{name}（包名 {bundle}）是一款本地工具类应用，主要功能：{feat_text}。</p>
  <h2>数据收集</h2>
  <p>本应用<strong>不收集</strong>可识别个人身份的信息。数据保存在设备本地（{persistence}），不会上传至我们的服务器。</p>
  <h2>第三方服务</h2>
  <p>本 MVP 不包含第三方广告或分析 SDK。</p>
  <h2>联系</h2>
  <p>如有疑问请联系：<a href="mailto:{email}">{email}</a></p>
  <p>商店描述：{store.get('subtitle', name)}</p>
</body>
</html>
"""


def _cf_token() -> str | None:
    return resolve_secret_value("CLOUDFLARE_API_TOKEN", settings.cloudflare_api_token)


def _cf_account() -> str | None:
    return resolve_secret_value("CLOUDFLARE_ACCOUNT_ID", settings.cloudflare_account_id)


def cf_pages_asset_hash(content: bytes, filename: str = "index.html") -> str:
    """Wrangler-compatible Pages asset hash (blake3 of base64+extension, 32 hex)."""
    try:
        import blake3
    except ImportError as exc:
        raise RuntimeError(
            "live CF Pages deploy requires the blake3 package; pip install blake3"
        ) from exc
    ext = PurePosixPath(filename).suffix.lstrip(".")
    payload = base64.b64encode(content).decode("ascii") + ext
    return blake3.blake3(payload.encode()).hexdigest()[:32]


def _cf_json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        return {"success": False, "errors": [{"message": response.text}]}
    if not body.get("success", False):
        errors = body.get("errors") or [{"message": response.text}]
        msg = "; ".join(str(e.get("message", e)) for e in errors)
        raise RuntimeError(msg)
    return body


def _ensure_cf_project(client: httpx.Client, base: str, headers: dict[str, str], project_name: str) -> None:
    create = client.post(
        base,
        headers=headers,
        json={"name": project_name, "production_branch": "main"},
    )
    if create.status_code in (200, 409):
        return
    _cf_json(create)


def _fetch_upload_jwt(
    client: httpx.Client,
    base: str,
    headers: dict[str, str],
    project_name: str,
) -> str:
    token_url = f"{base}/{project_name}/upload-token"
    resp = client.get(token_url, headers=headers)
    body = _cf_json(resp)
    jwt = (body.get("result") or {}).get("jwt")
    if not jwt:
        raise RuntimeError("CF upload-token response missing jwt")
    return str(jwt)


def _upload_cf_pages_file(
    client: httpx.Client,
    *,
    jwt: str,
    content: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Upload one static asset via Pages Direct Upload v2; return content hash."""
    file_hash = cf_pages_asset_hash(content, filename)
    auth = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}

    missing_resp = client.post(
        f"{_CF_API}/pages/assets/check-missing",
        headers=auth,
        json={"hashes": [file_hash]},
    )
    missing_body = _cf_json(missing_resp)
    missing_hashes = list(missing_body.get("result") or [])

    if file_hash in missing_hashes:
        upload_resp = client.post(
            f"{_CF_API}/pages/assets/upload",
            headers=auth,
            json=[
                {
                    "key": file_hash,
                    "value": base64.b64encode(content).decode("ascii"),
                    "metadata": {"contentType": content_type},
                    "base64": True,
                }
            ],
        )
        _cf_json(upload_resp)

    upsert_resp = client.post(
        f"{_CF_API}/pages/assets/upsert-hashes",
        headers=auth,
        json={"hashes": [file_hash]},
    )
    _cf_json(upsert_resp)
    return file_hash


def deploy_to_cloudflare_pages(
    project_name: str,
    html: str,
    *,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    effective_dry = settings.privacy_deploy_dry_run if dry_run is None else dry_run
    url = f"https://{project_name}.pages.dev/"
    if effective_dry:
        return {
            "ok": True,
            "dry_run": True,
            "url": url,
            "message": "privacy dry-run; set PRIVACY_DEPLOY_DRY_RUN=false for live deploy",
        }

    token = _cf_token()
    account = _cf_account()
    if not token or not account:
        return {
            "ok": False,
            "dry_run": False,
            "url": "",
            "message": "missing CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID",
        }

    headers = {"Authorization": f"Bearer {token}"}
    base = f"{_CF_API}/accounts/{account}/pages/projects"
    content = html.encode("utf-8")

    last_error = "unknown"
    for attempt in range(3):
        try:
            with httpx.Client(timeout=120.0) as client:
                _ensure_cf_project(client, base, headers, project_name)
                jwt = _fetch_upload_jwt(client, base, headers, project_name)
                file_hash = _upload_cf_pages_file(
                    client,
                    jwt=jwt,
                    content=content,
                    filename="index.html",
                    content_type="text/html; charset=utf-8",
                )
                manifest = json.dumps({"/index.html": file_hash})
                deploy = client.post(
                    f"{base}/{project_name}/deployments",
                    headers=headers,
                    data={"manifest": manifest},
                )
                _cf_json(deploy)
            return {"ok": True, "dry_run": False, "url": url, "message": "deployed to Cloudflare Pages"}
        except RuntimeError as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            return {"ok": False, "url": "", "message": last_error}
        except Exception as exc:
            last_error = f"CF deploy failed: {exc}"
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            return {"ok": False, "url": "", "message": last_error}
    return {"ok": False, "url": "", "message": last_error}


def ensure_privacy_url(
    req: dict[str, Any],
    workspace: Path,
) -> dict[str, Any]:
    """若 privacy_url 为占位符，生成 HTML 并部署，回写 store。"""
    store = req.setdefault("store", {})
    current = str(store.get("privacy_url") or "")
    if not is_placeholder_privacy_url(current):
        return {"ok": True, "url": current, "skipped": True}

    bundle = str((req.get("app") or {}).get("bundle_id") or "com.example.app")
    project_name = _slug_from_bundle(bundle)
    html = render_privacy_html(req)
    privacy_dir = workspace / "privacy"
    privacy_dir.mkdir(parents=True, exist_ok=True)
    (privacy_dir / "index.html").write_text(html, encoding="utf-8")

    result = deploy_to_cloudflare_pages(project_name, html)
    if result.get("ok") and result.get("url"):
        store["privacy_url"] = result["url"]
        req["store"] = store
        (privacy_dir / "deploy_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return result
