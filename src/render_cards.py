from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from models import CanvasSize, CoverSettings, OutputMode, RenderSettings, numbered_name

SUPPORTED_OVERLAY_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


class OverlayResolver:
    def __init__(
        self,
        overlay_dir: Path | None = None,
        fixed_image: Path | None = None,
    ) -> None:
        self.overlay_dir = overlay_dir
        self.fixed_image = fixed_image

    def resolve(self, index: int) -> Path | None:
        if self.overlay_dir:
            stems = [f"{index:04d}", f"{index:03d}"]
            for stem in stems:
                for ext in SUPPORTED_OVERLAY_EXTS:
                    direct = self.overlay_dir / f"{stem}{ext}"
                    if direct.exists():
                        return direct
                    upper = self.overlay_dir / f"{stem}{ext.upper()}"
                    if upper.exists():
                        return upper
        if self.fixed_image and self.fixed_image.exists():
            return self.fixed_image
        return None


def _default_image_workers() -> int:
    cpu = os.cpu_count() or 4
    return max(1, min(8, cpu))


def _text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=font)
    return right - left, bottom - top


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        width, _ = _text_bbox(draw, candidate, font)
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def _pick_font_and_lines(
    draw: ImageDraw.ImageDraw,
    sentence: str,
    settings: RenderSettings,
    text_width: int,
    text_height: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    font_size = settings.font_size
    while font_size >= settings.min_font_size:
        font = ImageFont.truetype(str(settings.font_path), size=font_size)
        lines = _wrap_text(draw, sentence, font, max_width=text_width)
        line_gap = int(font_size * (settings.line_spacing - 1))
        metrics = [_text_bbox(draw, line, font) for line in lines]
        total_height = sum(height for _, height in metrics) + line_gap * max(0, len(lines) - 1)
        if total_height <= text_height:
            return font, lines, line_gap
        font_size -= 1

    font = ImageFont.truetype(str(settings.font_path), size=settings.min_font_size)
    lines = _wrap_text(draw, sentence, font, max_width=text_width)
    line_gap = int(settings.min_font_size * (settings.line_spacing - 1))
    return font, lines, line_gap


def _fit_overlay(
    overlay: Image.Image,
    target_size: tuple[int, int],
    fit: str,
) -> Image.Image:
    target_w, target_h = target_size
    src_w, src_h = overlay.size
    if target_w <= 0 or target_h <= 0:
        return Image.new("RGB", (target_w, target_h), (0, 0, 0))

    if fit == "cover":
        scale = max(target_w / src_w, target_h / src_h)
    else:
        scale = min(target_w / src_w, target_h / src_h)
    resize_w = max(1, int(round(src_w * scale)))
    resize_h = max(1, int(round(src_h * scale)))
    resized = overlay.resize((resize_w, resize_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    x = (target_w - resize_w) // 2
    y = (target_h - resize_h) // 2
    canvas.paste(resized, (x, y))
    if fit == "cover":
        return canvas.crop((0, 0, target_w, target_h))
    return canvas


def _render_single_image(
    *,
    index: int,
    sentence: str,
    mode: OutputMode,
    size: CanvasSize,
    settings: RenderSettings,
    overlay_resolver: OverlayResolver,
    out_dir: Path,
    logger: logging.Logger | None,
) -> tuple[int, Path]:
    canvas = Image.new("RGB", (size.width, size.height), settings.bg_color)

    overlay_path = overlay_resolver.resolve(index)
    overlay_bottom = 0
    has_overlay = False
    if overlay_path is not None:
        overlay_height = int(round(size.height * settings.overlay_height_ratio))
        # Keep overlay as a square box for both portrait and landscape.
        overlay_side_by_width = int(round(size.width * settings.overlay_box_width_ratio))
        overlay_side = min(overlay_height, overlay_side_by_width)
        if mode == "landscape":
            # Make overlay visibly larger in horizontal videos.
            overlay_side = int(round(overlay_side * 1.35))
            overlay_side = min(overlay_side, size.width, size.height)
        if overlay_side > 0:
            has_overlay = True
            overlay_width = overlay_side
            overlay_height = overlay_side
            overlay_x = (size.width - overlay_width) // 2
            # Keep the overlay box centered on the whole canvas.
            overlay_y = (size.height - overlay_height) // 2
            with Image.open(overlay_path) as image:
                overlay = image.convert("RGB")
            fitted = _fit_overlay(
                overlay=overlay,
                target_size=(overlay_width, overlay_height),
                fit=settings.overlay_fit,
            )
            canvas.paste(fitted, (overlay_x, overlay_y))
            overlay_bottom = overlay_y + overlay_height

    text_top = overlay_bottom + settings.overlay_text_gap if has_overlay else 0
    text_height = size.height - text_top
    if text_height <= 0:
        text_top = 0
        text_height = size.height
        has_overlay = False

    text_width = size.width - settings.text_margin_x * 2
    text_box_height = text_height - settings.text_margin_y * 2
    if text_width <= 0 or text_box_height <= 0:
        raise ValueError("Text margins are too large for current canvas size.")

    draw = ImageDraw.Draw(canvas)
    font, lines, line_gap = _pick_font_and_lines(
        draw=draw,
        sentence=sentence,
        settings=settings,
        text_width=text_width,
        text_height=text_box_height,
    )

    metrics = [_text_bbox(draw, line, font) for line in lines]
    total_height = sum(height for _, height in metrics) + line_gap * max(0, len(lines) - 1)
    if has_overlay:
        # Keep text visually closer to overlay when image is present.
        y = text_top + min(settings.text_margin_y, 24)
    else:
        # No overlay: text is centered both horizontally and vertically on canvas.
        y = text_top + settings.text_margin_y + (text_box_height - total_height) // 2

    for line, (line_width, line_height) in zip(lines, metrics):
        x = (size.width - line_width) // 2
        draw.text((x, y), line, font=font, fill=settings.text_color)
        y += line_height + line_gap

    image_path = out_dir / numbered_name(index, "png")
    canvas.save(image_path, format="PNG")
    resolved = image_path.resolve()
    if logger:
        logger.info("%s image generated: %s", mode, image_path)
    return index, resolved


def render_images_for_mode(
    sentences: list[str],
    mode: OutputMode,
    size: CanvasSize,
    settings: RenderSettings,
    overlay_resolver: OverlayResolver,
    out_dir: Path,
    logger: logging.Logger | None = None,
    max_workers: int | None = None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    workers = max_workers or _default_image_workers()
    if workers <= 0:
        raise ValueError("max_workers for image rendering must be > 0")

    if len(sentences) <= 1 or workers == 1:
        results: dict[int, Path] = {}
        for index, sentence in enumerate(sentences, start=1):
            idx, path = _render_single_image(
                index=index,
                sentence=sentence,
                mode=mode,
                size=size,
                settings=settings,
                overlay_resolver=overlay_resolver,
                out_dir=out_dir,
                logger=logger,
            )
            results[idx] = path
        return [results[index] for index in range(1, len(sentences) + 1)]

    futures = {}
    results: dict[int, Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for index, sentence in enumerate(sentences, start=1):
            future = executor.submit(
                _render_single_image,
                index=index,
                sentence=sentence,
                mode=mode,
                size=size,
                settings=settings,
                overlay_resolver=overlay_resolver,
                out_dir=out_dir,
                logger=logger,
            )
            futures[future] = index

        for future in as_completed(futures):
            idx, path = future.result()
            results[idx] = path

    return [results[index] for index in range(1, len(sentences) + 1)]


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
