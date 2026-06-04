from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Android Play Store screenshot sizes (common devices)
SCREENSHOT_SIZES = [
    (1080, 1920),   # Standard phone portrait
    (1080, 2340),   # Tall phone
    (1440, 3120),   # Pixel style
]


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
        star_points = []
        for i in range(5):
            angle = i * 2 * 3.14159 / 5 - 3.14159 / 2
            outer_x = cx + shape_size * 0.7 * __import__("math").cos(angle)
            outer_y = cy + shape_size * 0.7 * __import__("math").sin(angle)
            star_points.extend([int(outer_x), int(outer_y)])
            inner_angle = angle + 3.14159 / 5
            inner_x = cx + shape_size * 0.3 * __import__("math").cos(inner_angle)
            inner_y = cy + shape_size * 0.3 * __import__("math").sin(inner_angle)
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


def _mock_material3_screenshot(
    width: int,
    height: int,
    *,
    app_name: str,
    subtitle: str,
    features: list[dict] | None,
    bg_hex: str,
) -> Image.Image:
    """Generate a phone-frame Material3 screenshot with status bar + nav bar."""
    bg = _hex_to_rgb(bg_hex)
    bg_dark = tuple(max(int(c * 0.15), 0) for c in bg)
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
        features = [{"title": "主功能", "items": ["功能项一", "功能项二", "功能项三"]}]

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
) -> list[str]:
    """Generate Material3-style mockup screenshots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for idx, (w, h) in enumerate(SCREENSHOT_SIZES):
        img = _mock_material3_screenshot(
            w, h,
            app_name=app_name,
            subtitle=subtitle,
            features=features,
            bg_hex=bg_hex,
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
