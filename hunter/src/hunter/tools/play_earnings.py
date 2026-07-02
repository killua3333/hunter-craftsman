"""Google Play 财务报告读取 — 从 Google Cloud Storage 获取 CSV 数据。

Google Play 的销售收入/回款数据通过 Cloud Storage bucket 按月提供（CSV zip 文件）：
  - 估算销售:  gs://[bucket-id]/sales/salesreport_YYYYMM.zip
  - 收入/回款:  gs://[bucket-id]/earnings/earnings_YYYYMM.zip

前提：
  1. 同一 Service Account 需在 Play Console 有"View financial data"权限（全局）
  2. 需 devstorage.read_only OAuth scope
  3. 需配置 PLAY_DEVELOPER_BUCKET_ID（例如 pubsite_prod_rev_0123456789）

提供 LangChain tool：
  play_get_earnings — 读取最新月份财务报告，返回聚合后的收入数据
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import zipfile
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_gcs_bucket_id() -> str | None:
    val = os.environ.get("PLAY_DEVELOPER_BUCKET_ID", "").strip()
    if not val:
        try:
            from craftsman.config import settings
            val = getattr(settings, "play_developer_bucket_id", "")
        except Exception:
            pass
    return val or None


def _build_gcs_client():
    """组建 GCS client，复用同一 Service Account + devstorage.read_only scope。"""
    from craftsman.publisher.play_client import service_account_info
    from google.oauth2 import service_account
    from google.cloud import storage

    # 优先: 读取 SA JSON
    info = service_account_info()
    if info is None:
        raise RuntimeError("GOOGLE_PLAY service account not configured")

    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/devstorage.read_only"],
    )
    return storage.Client(credentials=credentials)


def _list_report_files(client, bucket_id: str, prefix: str) -> list[str]:
    """列出指定 GCS bucket 前缀下的所有文件（按名称排序）。"""
    bucket = client.bucket(bucket_id)
    blobs = list(bucket.list_blobs(prefix=prefix))
    return sorted([b.name for b in blobs], reverse=True)


def _read_zip_csv(client, bucket_id: str, blob_name: str) -> list[dict[str, str]]:
    """从 GCS 下载 zip 文件，解压第一个 CSV 并读取全部行。"""
    bucket = client.bucket(bucket_id)
    blob = bucket.blob(blob_name)
    raw = blob.download_as_bytes()
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                with zf.open(name) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
                    rows.extend(list(reader))
                break  # 只读第一个 CSV
    return rows


def _aggregate_earnings(rows: list[dict[str, str]]) -> dict[str, Any]:
    """按 app package_name 聚合销售数据。"""
    per_app: dict[str, dict[str, float]] = {}
    total_gross = 0.0
    total_earnings = 0.0

    for row in rows:
        pkg = row.get("Product id") or row.get("Package Name") or "unknown"
        # 不同报告格式：earnings 有 Order Charged Amount 列，sales 有 Buyer Currency Amount with Tax
        charged_str = (
            row.get("Order Charged Amount")
            or row.get("Buyer Currency Amount with Tax")
            or row.get("Amount (Buyer Currency)")
            or "0"
        )
        try:
            charged = float(charged_str.replace(",", "").replace("$", "").strip())
        except (ValueError, AttributeError):
            charged = 0.0

        if pkg not in per_app:
            per_app[pkg] = {"gross_charged": 0.0, "transactions": 0}
        per_app[pkg]["gross_charged"] += charged
        per_app[pkg]["transactions"] += 1
        total_gross += charged

    # google takes 15% cut (simplified: 15% for first $1M, 30% above)
    total_earnings = round(total_gross * 0.85, 2)

    return {
        "total_gross": round(total_gross, 2),
        "total_earnings_estimated": total_earnings,
        "per_app": {k: {"gross": round(v["gross_charged"], 2), "transactions": v["transactions"]} for k, v in per_app.items()},
        "app_count": len(per_app),
    }


@tool
def play_get_earnings(
    months: int = 3,
) -> str:
    '''读取 Google Play 最近 N 个月的财务报告（销售+收入 CSV），按 app 聚合返回。

参数：
- months: 回溯月份数（默认 3，最多 12）

返回 JSON（含 total_gross, total_earnings_estimated, per_app 明细）。
'''
    bucket_id = _get_gcs_bucket_id()
    if not bucket_id:
        return json.dumps({
            "error": "PLAY_DEVELOPER_BUCKET_ID not configured",
            "hint": "在 .env 中设置 PLAY_DEVELOPER_BUCKET_ID（如 pubsite_prod_rev_0123456789），"
                    "并在 Play Console → 服务账号 → 勾选 'View financial data'（全局）",
        }, ensure_ascii=False)

    months = max(1, min(months, 12))
    now = datetime.now(timezone.utc)

    all_sales_rows: list[dict[str, str]] = []
    all_earnings_rows: list[dict[str, str]] = []

    try:
        client = _build_gcs_client()
    except Exception as exc:
        return json.dumps({"error": f"GCS client build failed: {exc}"}, ensure_ascii=False)

    try:
        for offset in range(months):
            year_month = (now.year, now.month - offset)
            if year_month[1] <= 0:
                year_month = (year_month[0] - 1, year_month[1] + 12)
            ym_str = f"{year_month[0]}{year_month[1]:02d}"

            # sales report
            try:
                sales_blobs = _list_report_files(client, bucket_id, f"sales/salesreport_{ym_str}")
                for blob_name in sales_blobs[:1]:  # 同月只取 1 个
                    try:
                        rows = _read_zip_csv(client, bucket_id, blob_name)
                        all_sales_rows.extend(rows)
                    except Exception:
                        logger.debug(f"读取 sales {blob_name} 失败")
            except Exception:
                logger.debug(f"sales/{ym_str} 不存在")
            # earnings report
            try:
                earnings_blobs = _list_report_files(client, bucket_id, f"earnings/earnings_{ym_str}")
                for blob_name in earnings_blobs[:1]:
                    try:
                        rows = _read_zip_csv(client, bucket_id, blob_name)
                        all_earnings_rows.extend(rows)
                    except Exception:
                        logger.debug(f"读取 earnings {blob_name} 失败")
            except Exception:
                logger.debug(f"earnings/{ym_str} 不存在")

    except Exception as exc:
        return json.dumps({"error": f"GCS 报告读取失败: {exc}"}, ensure_ascii=False)

    if not all_sales_rows and not all_earnings_rows:
        return json.dumps({
            "total_gross": 0,
            "total_earnings_estimated": 0,
            "per_app": {},
            "app_count": 0,
            "months_scanned": months,
            "note": "最近 N 个月无财务报告（可能是未产生销售收入，或 bucket 尚未生成报告）",
        }, ensure_ascii=False, indent=2)

    sales_agg = _aggregate_earnings(all_sales_rows) if all_sales_rows else {}
    earnings_agg = _aggregate_earnings(all_earnings_rows) if all_earnings_rows else {}

    return json.dumps({
        "sales": sales_agg,
        "earnings": earnings_agg,
        "months_scanned": months,
        "summary": (
            f"扫描 {months} 个月财务报告。"
            f"销售估算: {sales_agg.get('total_gross', 0)} USD。"
            f"回款估算: {earnings_agg.get('total_earnings_estimated', 0)} USD。"
            f"覆盖 {sales_agg.get('app_count', 0)} 个 app。"
        ),
    }, ensure_ascii=False, indent=2)
