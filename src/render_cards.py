from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from models import CanvasSize, CoverSettings, OutputMode


def _text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=font)
    return right - left, bottom - top


def _truncate_keyword(keyword: str, max_chars: int = 12) -> str:
    cleaned = (keyword or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}..."


def _fit_cover_font(
    draw: ImageDraw.ImageDraw,
    title_text: str,
    font_path: Path,
    width: int,
    height: int,
    width_limit_ratio: float,
    height_limit_ratio: float,
) -> ImageFont.FreeTypeFont:
    # Use conservative size to keep title inside portrait-safe area.
    base = int(min(width, height) * 0.10)
    min_size = 22
    for size in range(base, min_size - 1, -2):
        unified_size = max(min_size, int(size * 1.25))
        title_font = ImageFont.truetype(str(font_path), size=unified_size)

        title_w, title_h = _text_bbox(draw, title_text, title_font)
        if title_w <= int(width * width_limit_ratio) and title_h <= int(height * height_limit_ratio):
            return title_font

    fallback_size = max(min_size, int(min_size * 1.25))
    return ImageFont.truetype(str(font_path), size=fallback_size)


def render_cover_image(
    *,
    mode: OutputMode,
    size: CanvasSize,
    settings: CoverSettings,
    theme_keyword: str,
    font_path: Path,
    out_dir: Path,
    logger: logging.Logger | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    keyword = _truncate_keyword(theme_keyword)
    title_text = f"\u300a{keyword}\u300b"
    canvas = Image.new("RGB", (size.width, size.height), settings.bg_color)
    draw = ImageDraw.Draw(canvas)
    is_portrait = size.height >= size.width

    title_font = _fit_cover_font(
        draw=draw,
        title_text=title_text,
        font_path=font_path,
        width=size.width,
        height=size.height,
        width_limit_ratio=0.72 if is_portrait else 0.84,
        height_limit_ratio=0.56 if is_portrait else 0.62,
    )

    title_w, title_h = _text_bbox(draw, title_text, title_font)
    y = (size.height - title_h) // 2
    draw.text(
        ((size.width - title_w) // 2, y),
        title_text,
        font=title_font,
        fill=settings.text_color,
    )

    output = (out_dir / "0000_cover.png").resolve()
    canvas.save(output, format="PNG")
    if logger:
        logger.info("%s cover image generated: %s", mode, output)
    return output
