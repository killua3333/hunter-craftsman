"""生成 Windows 可直接双击打开的交互式 Web Demo（workspace/index.html）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from craftsman.config import ROOT

logger = logging.getLogger(__name__)

_TEMPLATES = ROOT / "templates" / "web-demo"
_LOADER = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(enabled_extensions=("html", "j2")),
)


def detect_demo_kind(req: dict[str, Any]) -> str:
    blob = json.dumps(req, ensure_ascii=False).lower()
    timer_keys = ("番茄", "pomodoro", "倒计时", "计时", "timer", "专注")
    converter_keys = ("单位换算", "换算", "converter", "单位转换")
    calc_keys = ("计算器", "calculator", "四则", "运算")
    if any(k in blob for k in timer_keys):
        return "timer"
    if any(k in blob for k in converter_keys):
        return "converter"
    if any(k in blob for k in calc_keys):
        return "calculator"
    return "list"


def _demo_context(req: dict[str, Any]) -> dict[str, Any]:
    app = req.get("app") or {}
    branding = req.get("branding") or {}
    store = req.get("store") or {}
    features = req.get("features") or []
    items: list[str] = []
    for feat in features:
        for item in feat.get("items") or []:
            items.append(str(item))
    primary = branding.get("primary_color", "#007AFF")
    return {
        "app_name": app.get("name", "Craftsman App"),
        "subtitle": store.get("subtitle", ""),
        "primary_color": primary,
        "accent_color": branding.get("accent_color", "#2ECC71"),
        "break_color": branding.get("break_color", "#3498DB"),
        "warning_color": branding.get("warning_color", "#F39C12"),
        "items": items or ["示例条目 1", "示例条目 2"],
        "persistence": (req.get("core_logic") or {}).get("persistence", "none"),
    }


def _is_interactive_html(path: Path) -> bool:
    """判断 HTML 是否由 LLM 生成且具有真实交互逻辑。

    要求同时满足：（1）含 <script 标签；（2）体积 > 1500 字节；
    （3）不含模板占位符 {{ }}。
    """
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    has_script = "<script" in text.lower()
    big_enough = len(text) > 1500
    no_template = "{{" not in text
    return has_script and big_enough and no_template


def generate_interactive_demo(workspace: Path, req: dict[str, Any]) -> Path:
    """渲染并写入 workspace/index.html，返回路径。"""
    kind = detect_demo_kind(req)
    tpl = _LOADER.get_template(f"{kind}.html.j2")
    html = tpl.render(**_demo_context(req))
    out = workspace / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def ensure_windows_demo(workspace: Path, req: dict[str, Any]) -> Path:
    """
    保证 workspace 根目录存在可交互的 index.html。
    若 LLM 已生成合格页面则保留，否则按需求类型渲染模板。
    """
    index_path = workspace / "index.html"
    if _is_interactive_html(index_path):
        logger.info("web_demo: keeping LLM-generated index.html (%d bytes)", index_path.stat().st_size)
        return index_path
    logger.warning("web_demo: LLM codegen produced no valid HTML, falling back to template")
    return generate_interactive_demo(workspace, req)


def write_artifacts_redirect(artifacts_demo_path: Path) -> None:
    """artifacts/demo.html 跳转到根目录交互 Demo。"""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="0; url=../index.html" />
  <title>打开 Demo</title>
</head>
<body>
  <p>正在打开交互演示…若未跳转，请<a href="../index.html">点击这里</a>。</p>
</body>
</html>
"""
    artifacts_demo_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_demo_path.write_text(html, encoding="utf-8")
