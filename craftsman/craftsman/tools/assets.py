from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Android Play Store screenshot sizes (common devices)
SCREENSHOT_SIZES = [
    (1080, 1920),   # Standard phone portrait
    (1080, 2340),   # Tall phone
    (1440, 3120),   # Pixel style
]

# ── B3: 按品类预置色板 ──
PRESET_PALETTES: dict[str, dict[str, str]] = {
    "tools": {
        "primary": "#546E7A",
        "primary_dark": "#37474F",
        "secondary": "#78909C",
    },
    "health": {
        "primary": "#43A047",
        "primary_dark": "#2E7D32",
        "secondary": "#81C784",
    },
    "finance": {
        "primary": "#FB8C00",
        "primary_dark": "#EF6C00",
        "secondary": "#FFB74D",
    },
    "notes": {
        "primary": "#5C6BC0",
        "primary_dark": "#3949AB",
        "secondary": "#7986CB",
    },
}

# 品类关键词 → 色板映射
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "tools": ["tool", "工具", "utility", "utilities", "converter", "换算", "calculator", "计算", "file", "文件", "manager", "管理", "cleaner", "清理"],
    "health": ["health", "fitness", "健康", "运动", "workout", "diet", "跑步", "pedometer", "计步", "meditation", "冥想", "sleep", "睡眠"],
    "finance": ["finance", "金融", "financial", "expense", "记账", "budget", "预算", "money", "stock", "股票", "crypto", "tax", "税"],
    "notes": ["note", "笔记", "todo", "task", "清单", "reminder", "备忘", "checklist", "planner", "计划", "journal", "日记", "habit", "习惯"],
}


def choose_palette(app_name_or_type: str = "", features: list[str] | None = None) -> dict[str, str]:
    """根据 app 名称/功能关键词自动匹配品类色板。

    返回 {"primary": "#...", "primary_dark": "...", "secondary": "..."}
    未匹配时默认返回 tools 色板。
    """
    text = (app_name_or_type or "").lower()
    features_lower = [f.lower() for f in (features or [])]
    combined = f"{text} {' '.join(features_lower)}"

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in combined:
                return PRESET_PALETTES.get(category, PRESET_PALETTES["tools"])
    # 也检查 app type 是否为预设品类名
    if text and text in PRESET_PALETTES:
        return PRESET_PALETTES[text]
    return PRESET_PALETTES["tools"]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _choose_icon_shape(app_name: str) -> str:
    """Pick a simple icon shape based on app name hash (deterministic per app)."""
    digest = hashlib.md5(app_name.encode()).hexdigest()
    idx = int(digest[:2], 16) % 5
    return ["circle", "diamond", "triangle", "square", "star"][idx]


def _app_name_letter(app_name: str) -> str:
    """First meaningful character of app name for icon text."""
    for ch in app_name:
        if ch.isalpha() or '\u4e00' <= ch <= '\u9fff':
            return ch
    return app_name[0] if app_name else "A"


def generate_icon(out_path: Path, *, text: str, bg_hex: str) -> None:
    """Generate a modern Android app icon: rounded rect + simple shape + letter."""
    size = 512  # App icon base size
    bg_rgb = _hex_to_rgb(bg_hex)
    letter = _app_name_letter(text)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background: rounded rectangle with gradient effect
    margin = 0
    # Draw main rounded rect
    radius_bg = int(size * 0.18)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius_bg,
        fill=bg_rgb,
    )

    # Inner lighter highlight (top-left gradient effect)
    lighter = tuple(min(c + 60, 255) for c in bg_rgb)
    highlight_radius = int(size * 0.15)
    draw.rounded_rectangle(
        [int(size * 0.08), int(size * 0.08),
         int(size * 0.92), int(size * 0.65)],
        radius=highlight_radius,
        fill=lighter,
    )

    # Shape in center
    shape = _choose_icon_shape(text)
    cx, cy = size // 2, size // 2
    shape_size = int(size * 0.28)

    if shape == "circle":
        draw.ellipse(
            [cx - shape_size, cy - shape_size, cx + shape_size, cy + shape_size],
            fill=(255, 255, 255, 240),
        )
    elif shape == "diamond":
        draw.polygon(
            [(cx, cy - shape_size), (cx + shape_size, cy),
             (cx, cy + shape_size), (cx - shape_size, cy)],
            fill=(255, 255, 255, 240),
        )
    elif shape == "triangle":
        draw.polygon(
            [(cx, cy - shape_size),
             (cx + shape_size, cy + shape_size),
             (cx - shape_size, cy + shape_size)],
            fill=(255, 255, 255, 240),
        )
    elif shape == "square":
        draw.rounded_rectangle(
            [cx - shape_size, cy - shape_size, cx + shape_size, cy + shape_size],
            radius=int(shape_size * 0.2),
            fill=(255, 255, 255, 240),
        )
    else:  # star
        import math
        star_points = []
        for i in range(5):
            angle = i * 2 * math.pi / 5 - math.pi / 2
            outer_x = cx + shape_size * 0.7 * math.cos(angle)
            outer_y = cy + shape_size * 0.7 * math.sin(angle)
            star_points.extend([int(outer_x), int(outer_y)])
            inner_angle = angle + math.pi / 5
            inner_x = cx + shape_size * 0.3 * math.cos(inner_angle)
            inner_y = cy + shape_size * 0.3 * math.sin(inner_angle)
            star_points.extend([int(inner_x), int(inner_y)])
        draw.polygon(star_points, fill=(255, 255, 255, 240))

    # Letter overlay
    try:
        font = ImageFont.truetype("arial.ttf", int(size * 0.35))
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2, (size - th) / 2 + size * 0.06),
        letter,
        fill=bg_rgb,
        font=font,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


# ── B1: LLM 生成 SVG 图标 ──

def _extract_svg_from_llm_response(text: str) -> str | None:
    """从 LLM 返回中提取 SVG 标签。"""
    # 尝试提取 ```svg ... ``` 代码块
    m = re.search(r'```(?:svg|xml)?\s*(<svg[\s\S]*?</svg>)\s*```', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 尝试直接匹配 <svg ... </svg>
    m = re.search(r'(<svg[\s\S]*?</svg>)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _validate_svg(svg_str: str) -> bool:
    """验证 SVG 字符串是否合法。"""
    try:
        svg_str_clean = re.sub(r'<!--[\s\S]*?-->', '', svg_str)
        ET.fromstring(svg_str_clean)
        return True
    except ET.ParseError:
        return False


def _svg_to_png_icons(svg_str: str, out_dir: Path, sizes: list[int] | None = None) -> list[str]:
    """将 SVG 字符串渲染为多个尺寸的 PNG 图标。

    使用 CairoSVG（优先）或纯 Pillow 方案。
    返回生成的文件路径列表。
    """
    if sizes is None:
        sizes = [512, 192, 144, 96, 72, 48]
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # 尝试 cairosvg
    try:
        import cairosvg
        for sz in sizes:
            out_path = out_dir / f"ic_launcher_{sz}x{sz}.png"
            cairosvg.svg2png(
                bytestring=svg_str.encode("utf-8"),
                write_to=str(out_path),
                output_width=sz,
                output_height=sz,
            )
            paths.append(str(out_path))
        return paths
    except ImportError:
        logger.debug("cairosvg not available, falling back to Pillow rendering")
    except Exception:
        logger.debug("cairosvg rendering failed, falling back to Pillow")

    # 回退: 使用 Pillow 渲染 (基础 — 只能处理 viewBox 和简单 shapes)
    try:
        import math as _math
        svg_ns = {"svg": "http://www.w3.org/2000/svg"}
        root = ET.fromstring(svg_str)
        # 尝试获取 viewBox
        vb = root.get("viewBox", "0 0 512 512")
        parts = vb.replace(",", " ").split()
        if len(parts) >= 4:
            vb_w, vb_h = float(parts[2]), float(parts[3])
        else:
            vb_w = vb_h = 512.0

        for sz in sizes:
            img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            scale_x = sz / vb_w
            scale_y = sz / vb_h

            # 递归渲染基本形状
            def _render(elem, el_scale_x=scale_x, el_scale_y=scale_y):
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                fill = elem.get("fill", "none")
                stroke = elem.get("stroke", "none")
                stroke_w = float(elem.get("stroke-width", "1"))

                if fill == "none" and stroke == "none":
                    fill = "#000000"

                try:
                    fill_rgb = _parse_svg_color(fill)
                except Exception:
                    fill_rgb = (0, 0, 0, 255)

                if tag == "rect":
                    x = float(elem.get("x", 0)) * el_scale_x
                    y = float(elem.get("y", 0)) * el_scale_y
                    w = float(elem.get("width", vb_w)) * el_scale_x
                    h = float(elem.get("height", vb_h)) * el_scale_y
                    rx = float(elem.get("rx", 0))
                    ry = float(elem.get("ry", 0))
                    if rx or ry:
                        draw.rounded_rectangle(
                            [x, y, x + w, y + h],
                            radius=max(rx * el_scale_x, ry * el_scale_y),
                            fill=fill_rgb,
                        )
                    else:
                        draw.rectangle([x, y, x + w, y + h], fill=fill_rgb)
                elif tag == "circle":
                    cx = float(elem.get("cx", 0)) * el_scale_x
                    cy = float(elem.get("cy", 0)) * el_scale_y
                    r = float(elem.get("r", 50)) * min(el_scale_x, el_scale_y)
                    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill_rgb)
                elif tag == "polygon":
                    points_str = elem.get("points", "")
                    pts = [float(p) for p in points_str.replace(",", " ").split()]
                    scaled = [(pts[i] * el_scale_x, pts[i + 1] * el_scale_y) for i in range(0, len(pts), 2)]
                    draw.polygon(scaled, fill=fill_rgb)

                for child in elem:
                    _render(child, el_scale_x, el_scale_y)

            _render(root)
            out_path = out_dir / f"ic_launcher_{sz}x{sz}.png"
            img.save(out_path, "PNG")
            paths.append(str(out_path))
        return paths
    except Exception as exc:
        logger.warning(f"Pillow SVG fallback render failed: {exc}")
        return []


def _parse_svg_color(val: str) -> tuple[int, int, int, int]:
    """解析 SVG 颜色值，返回 (R, G, B, A)。"""
    val = (val or "").strip()
    if val in ("none", "transparent"):
        return (0, 0, 0, 0)
    if val.startswith("#"):
        val = val.lstrip("#")
        if len(val) == 3:
            val = "".join(c * 2 for c in val)
        if len(val) == 6:
            return (int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16), 255)
        if len(val) == 8:
            return (int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16), int(val[6:8], 16))
    # named colors
    common = {
        "white": (255, 255, 255, 255), "black": (0, 0, 0, 255),
        "red": (255, 0, 0, 255), "green": (0, 128, 0, 255),
        "blue": (0, 0, 255, 255), "yellow": (255, 255, 0, 255),
        "orange": (255, 165, 0, 255), "purple": (128, 0, 128, 255),
    }
    return common.get(val.lower(), (128, 128, 128, 255))


def generate_icon_via_llm(
    out_path: Path,
    *,
    app_name: str = "",
    branding_text: str = "",
    features: list[str] | None = None,
    palette: dict[str, str] | None = None,
) -> list[str]:
    """通过 LLM 生成 SVG 图标，渲染为多尺寸 PNG。

    返回所有生成 PNG 路径的列表（含 512x512 主图）。
    如果 LLM 调用失败或 SVG 不合法，回退到传统 generate_icon。
    """
    features_list = features or []
    palette = palette or PRESET_PALETTES["tools"]

    # 构建 LLM prompt
    feature_str = "\n".join(f"  - {f}" for f in features_list[:5]) if features_list else "  - Minimal utility app"
    primary = palette.get("primary", "#546E7A")
    secondary = palette.get("secondary", "#78909C")

    prompt_parts = [
        f"Generate a clean, modern Android app icon as a single SVG for an app named \"{app_name}\".",
        f"Icon text/branding: \"{branding_text or app_name[:1]}\"",
        f"Colors to use: primary={primary}, secondary={secondary}",
        f"Features of the app:\n{feature_str}",
        "Requirements:",
        "- MUST be a single <svg> element with viewBox=\"0 0 512 512\"",
        "- Use ONLY basic shapes: <rect>, <circle>, <polygon>, and <path>",
        "- Limit to 3 colors (including background)",
        "- Rounded corners preferred for modern Android look (rx/ry on rects)",
        "- Output ONLY the SVG code, no explanations, no markdown",
    ]

    svg_str = None
    try:
        from craftsman.config import settings
        from craftsman.llm import _client

        client = _client()
        if client is None:
            raise RuntimeError("LLM client not available (no API key)")
        resp = client.chat.completions.create(
            model=settings.deepseek_chat_model,
            messages=[
                {"role": "system", "content": "You are an expert Android app icon designer. Output ONLY valid SVG code."},
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        raw = resp.choices[0].message.content or ""
        svg_str = _extract_svg_from_llm_response(raw)
        if svg_str and _validate_svg(svg_str):
            logger.info(f"LLM generated valid SVG icon for {app_name}")
        else:
            svg_str = None
    except Exception as exc:
        logger.warning(f"LLM icon generation failed: {exc}, falling back to traditional method")

    if not svg_str:
        # 回退：传统 generate_icon
        bg_hex = palette.get("primary", "#546E7A")
        generate_icon(out_path, text=(branding_text or app_name), bg_hex=bg_hex)
        return [str(out_path)]

    # 渲染多尺寸 PNG
    out_dir = out_path.parent
    png_paths = _svg_to_png_icons(svg_str, out_dir)
    if not png_paths:
        # 渲染失败，回退
        bg_hex = palette.get("primary", "#546E7A")
        generate_icon(out_path, text=(branding_text or app_name), bg_hex=bg_hex)
        return [str(out_path)]

    # 确保 512 主图也存在
    main_512 = str(out_dir / "ic_launcher_512x512.png")
    if main_512 not in png_paths:
        # 渲染一个主图
        _svg_to_png_icons(svg_str, out_dir, sizes=[512])
        png_paths.append(str(out_dir / "ic_launcher_512x512.png"))

    return png_paths


# ── Screenshots ──

def _mock_material3_screenshot(
    width: int,
    height: int,
    *,
    app_name: str,
    subtitle: str,
    features: list[dict] | None,
    bg_hex: str,
    benefit_text: str = "",
    palette: dict[str, str] | None = None,
) -> Image.Image:
    """Generate a phone-frame Material3 screenshot with status bar + nav bar.

    B4 enhancement: support benefit_text overlay and palette-driven dark background.
    """
    palette = palette or {}
    bg_dark_override = palette.get("primary_dark")
    bg = _hex_to_rgb(bg_hex)
    bg_dark = _hex_to_rgb(bg_dark_override) if bg_dark_override else tuple(max(int(c * 0.15), 0) for c in bg)
    card_bg = (255, 255, 255)
    text_primary = (30, 30, 30)
    text_secondary = (100, 100, 100)
    accent = bg
    white = (255, 255, 255)

    img = Image.new("RGB", (width, height), bg_dark)
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("arial.ttf", int(height * 0.025))
        body_font = ImageFont.truetype("arial.ttf", int(height * 0.019))
        small_font = ImageFont.truetype("arial.ttf", int(height * 0.016))
        micro_font = ImageFont.truetype("arial.ttf", int(height * 0.013))
    except OSError:
        title_font = ImageFont.load_default()
        body_font = title_font
        small_font = title_font
        micro_font = title_font

    padding = int(width * 0.06)
    card_padding = int(width * 0.04)
    card_radius = int(height * 0.015)
    screen_left = 0
    screen_top = 0

    # ── Android Status Bar ──
    status_h = int(height * 0.042)
    draw.rectangle([0, 0, width, status_h], fill=bg)
    status_y = int(status_h * 0.22)
    # Time
    draw.text((int(width * 0.06), status_y), "9:41", fill=white, font=micro_font)
    # Signal / Battery indicators (right side)
    right_x = width - int(width * 0.08)
    draw.text((right_x - 60, status_y), "5G", fill=white, font=micro_font)
    draw.text((right_x - 30, status_y), "🔋", fill=white, font=micro_font)
    draw.text((right_x, status_y), "100%", fill=white, font=micro_font)

    # ── App Top Bar (Material3) ──
    top_bar_h = int(height * 0.065)
    top_bar_y = status_h
    draw.rectangle([0, top_bar_y, width, top_bar_y + top_bar_h], fill=bg)
    draw.text(
        (padding, top_bar_y + int(top_bar_h * 0.28)),
        app_name,
        fill=(255, 255, 255),
        font=title_font,
    )

    # ── Content Area ──
    content_top = top_bar_y + top_bar_h
    content_h = height - content_top - int(height * 0.058)
    # Subtle background gradient strip
    draw.rectangle([0, content_top, width, content_top + content_h], fill=(248, 249, 252))

    y = content_top + int(height * 0.015)

    # Subtitle row
    subtitle_h = int(height * 0.045)
    draw.rounded_rectangle(
        [padding, y, width - padding, y + subtitle_h],
        radius=card_radius,
        fill=card_bg,
    )
    draw.text(
        (padding + card_padding, y + card_padding // 2),
        subtitle or app_name,
        fill=text_secondary,
        font=small_font,
    )
    y += subtitle_h + int(height * 0.015)

    # Feature cards
    features = features or []
    if not features:
        features = [{"title": "主功能", "items": ["核心功能一", "核心功能二", "核心功能三"]}]

    max_y = content_top + content_h - int(height * 0.04)
    for feat in features[:6]:
        if not isinstance(feat, dict):
            continue
        feat_title = str(feat.get("title") or "功能")
        items = feat.get("items") or []
        if isinstance(items, str):
            items = [items]
        items = [str(it) for it in items][:4]

        item_count = len(items) or 1
        card_h = int(height * 0.04) + item_count * int(height * 0.03)

        if y + card_h > max_y:
            break

        # Card background
        draw.rounded_rectangle(
            [padding, y, width - padding, y + card_h],
            radius=card_radius,
            fill=card_bg,
        )

        # Accent bar on left
        bar_w = int(width * 0.01)
        draw.rectangle(
            [padding, y + int(card_h * 0.15), padding + bar_w, y + card_h - int(card_h * 0.15)],
            fill=accent,
        )

        # Title
        title_x = padding + card_padding + bar_w + int(width * 0.01)
        draw.text(
            (title_x, y + card_padding),
            feat_title,
            fill=text_primary,
            font=body_font,
        )

        # Items
        item_y = y + card_padding + int(height * 0.028)
        for item in items:
            draw.text(
                (title_x + int(width * 0.015), item_y),
                f"• {item}",
                fill=text_secondary,
                font=small_font,
            )
            item_y += int(height * 0.028)

        y += card_h + int(height * 0.015)

    # ── B4: Benefit text 底部叠加 ──
    if benefit_text:
        benefit_y = max_y - int(height * 0.025)
        # 半透明背景条
        overlay_y = benefit_y - int(height * 0.01)
        overlay_h = int(height * 0.04)
        draw.rectangle([0, overlay_y, width, overlay_y + overlay_h], fill=(0, 0, 0, 120))
        draw.text(
            (int(width * 0.08), benefit_y),
            benefit_text,
            fill=(255, 255, 255),
            font=micro_font,
        )

    # ── Android Navigation Bar ──
    nav_y = height - int(height * 0.058)
    draw.rectangle([0, nav_y, width, height], fill=(20, 20, 22))
    nav_center = nav_y + int((height - nav_y) * 0.5)
    # Home pill
    pill_w = int(width * 0.15)
    pill_h = int(height * 0.006)
    draw.rounded_rectangle(
        [(width - pill_w) // 2, nav_center - pill_h // 2,
         (width + pill_w) // 2, nav_center + pill_h // 2],
        radius=pill_h // 2,
        fill=(180, 180, 185),
    )

    return img


def generate_screenshots(
    out_dir: Path,
    *,
    app_name: str,
    subtitle: str,
    bg_hex: str,
    features: list[dict] | None = None,
    benefit_text: str = "",
    palette: dict[str, str] | None = None,
) -> list[str]:
    """Generate Material3-style mockup screenshots.

    B4 enhancement: benefit_text and palette params for enhanced visuals.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for idx, (w, h) in enumerate(SCREENSHOT_SIZES):
        img = _mock_material3_screenshot(
            w, h,
            app_name=app_name,
            subtitle=subtitle,
            features=features,
            bg_hex=bg_hex,
            benefit_text=benefit_text,
            palette=palette,
        )
        path = out_dir / f"screenshot_{idx + 1}.png"
        img.save(path, "PNG")
        paths.append(str(path))
    return paths


def generate_demo_html(
    out_path: Path,
    *,
    app_name: str,
    subtitle: str,
    core_logic: str,
    ui_layout: str,
    screenshots: list[str],
) -> str:
    """生成可在 Windows 直接打开的静态 Demo 页面。"""
    image_blocks = []
    for img in screenshots:
        rel = Path(img).name
        image_blocks.append(f'<img src="screenshots/{rel}" alt="{app_name}" />')
    images_html = "\n".join(image_blocks) if image_blocks else "<p>暂无截图</p>"

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{app_name} Demo</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; background: #f7f9fc; color: #202737; }}
    .card {{ background: white; border-radius: 14px; padding: 20px; margin-bottom: 16px; box-shadow: 0 3px 16px rgba(0,0,0,.08); }}
    .shots {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    img {{ width: 100%; border-radius: 10px; border: 1px solid #dde4f0; }}
    h1 {{ margin: 0 0 8px 0; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{app_name}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="card">
    <h2>核心逻辑</h2>
    <p>{core_logic}</p>
    <h2>UI 布局</h2>
    <p>{ui_layout}</p>
  </div>
  <div class="card">
    <h2>Demo 截图</h2>
    <div class="shots">{images_html}</div>
  </div>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
