from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# App Store screenshot widths (portrait height derived ~19.5:9)
SCREENSHOT_SIZES = [
    (1290, 2796),
    (1284, 2778),
    (1242, 2688),
]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def generate_icon(out_path: Path, *, text: str, bg_hex: str) -> None:
    size = 1024
    img = Image.new("RGB", (size, size), _hex_to_rgb(bg_hex))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 400)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2), text, fill=(255, 255, 255), font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


def generate_screenshots(
    out_dir: Path,
    *,
    app_name: str,
    subtitle: str,
    bg_hex: str,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for idx, (w, h) in enumerate(SCREENSHOT_SIZES):
        img = Image.new("RGB", (w, h), _hex_to_rgb(bg_hex))
        draw = ImageDraw.Draw(img)
        try:
            title_font = ImageFont.truetype("arial.ttf", int(h * 0.05))
            sub_font = ImageFont.truetype("arial.ttf", int(h * 0.03))
        except OSError:
            title_font = ImageFont.load_default()
            sub_font = title_font
        draw.text((w * 0.08, h * 0.35), app_name, fill=(255, 255, 255), font=title_font)
        draw.text((w * 0.08, h * 0.42), subtitle, fill=(220, 220, 220), font=sub_font)
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
