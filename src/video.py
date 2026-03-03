from __future__ import annotations

import logging
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import ImageFont
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    vfx,
)
from ffmpeg_utils import run_cmd
from moviepy.audio.AudioClip import AudioClip

from models import AudioItem, CanvasSize, OutputMode, RenderSettings, numbered_name

MAX_CLIP_RETRIES = 3

# Supported text effect names for cycling.
SUPPORTED_EFFECTS = ("fadein", "fadeout", "slide_left", "slide_right", "slide_top", "slide_bottom", "rotate")
LYRICS_CONTEXT_OPACITY = 0.35
LYRICS_VISIBLE_LINES = 5
LYRICS_CURRENT_SCALE = 1.5
LYRICS_CURRENT_MAX_WIDTH_RATIO = 0.92


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color string like '#FF0000' to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _default_clip_workers() -> int:
    cpu = os.cpu_count() or 4
    return max(1, min(4, cpu))


def _silent_audio(duration: float, fps: int = 44100) -> AudioClip:
    """Create a silent audio clip of the given duration."""
    return AudioClip(
        lambda t: [0, 0],
        duration=duration,
        fps=fps,
    )


_previous_color: str | None = None

def _pick_text_color(index: int, settings: RenderSettings) -> str:
    """Pick text color: first is static text_color, subseq pick random text_colors w/o dupes."""
    global _previous_color

    # If random_color is disabled, always use the primary text_color
    if not settings.random_color:
        _previous_color = settings.text_color
        return settings.text_color

    # 1. The first sentence uses the primary config color (typically white)
    if index == 1:
        _previous_color = settings.text_color
        return settings.text_color

    # 2. If no available text_colors sequence is set, fallback to the text_color
    if not settings.text_colors:
        _previous_color = settings.text_color
        return settings.text_color

    # 3. Only one color configured
    if len(settings.text_colors) == 1:
        picked = settings.text_colors[0]
        _previous_color = picked
        return picked

    # 4. Filter colors to exclude the previous color, then randomly choose one of them.
    # We must explicitly import random somewhere at the file level, we will do it locally or at top
    import random
    available_colors = [c for c in settings.text_colors if c != _previous_color]
    if not available_colors:
        # Edge case: all matching or something unexpected
        available_colors = list(settings.text_colors)

    picked = random.choice(available_colors)
    _previous_color = picked
    return picked


_previous_effect: str | None = None

def _pick_effect_name(index: int, settings: RenderSettings) -> str | None:
    """Pick an effect name by randomly choosing from text_effects, avoiding dupes."""
    global _previous_effect

    # If use_text_effects is disabled, always return None (no effect)
    if not settings.use_text_effects:
        return None

    # If text_effects is empty, return None
    if not settings.text_effects:
        return None

    # If random_effect is disabled, use the first effect cyclically
    if not settings.random_effect:
        effect_index = (index - 1) % len(settings.text_effects)
        picked = settings.text_effects[effect_index]
        _previous_effect = picked
        return picked

    # Random effect mode
    if len(settings.text_effects) == 1:
        return settings.text_effects[0]

    import random
    available_effects = [e for e in settings.text_effects if e != _previous_effect]
    if not available_effects:
        available_effects = list(settings.text_effects)

    picked = random.choice(available_effects)
    _previous_effect = picked
    return picked


def _apply_text_effect(
    text_clip: TextClip,
    effect_name: str | None,
    effect_duration: float,
    canvas_width: int,
    canvas_height: int,
) -> tuple[TextClip, bool]:
    """Apply a single text effect to the TextClip.

    Returns
    -------
    (clip, handles_position) – *handles_position* is True when the effect
    already sets the clip position (slide effects).  The caller must NOT
    call ``with_position`` again in that case.
    """
    if not effect_name:
        return text_clip, False

    name = effect_name.lower().strip()

    # --- pixel-based effects (don't touch position) --------------------------
    if name == "fadein":
        return text_clip.with_effects([vfx.FadeIn(effect_duration)]), False
    elif name == "fadeout":
        return text_clip.with_effects([vfx.FadeOut(effect_duration)]), False
    elif name == "rotate":
        # Animated rotation: eases from 15° to 0° over effect_duration.
        start_angle = 15.0
        def _rotation_angle(t: float) -> float:
            if t >= effect_duration:
                return 0.0
            progress = t / effect_duration
            return start_angle * (1.0 - progress)
        return text_clip.with_effects(
            [vfx.Rotate(_rotation_angle, expand=False)]
        ), False

    # --- position-based effects (custom slide to center) ---------------------
    clip_w, clip_h = text_clip.size
    center_x = (canvas_width - clip_w) / 2.0
    center_y = (canvas_height - clip_h) / 2.0

    if name == "slide_left":
        def _pos(t: float) -> tuple[float, float]:
            progress = min(t / effect_duration, 1.0)
            x = -clip_w + (center_x + clip_w) * progress
            return (x, center_y)
        return text_clip.with_position(_pos), True
    elif name == "slide_right":
        def _pos(t: float) -> tuple[float, float]:
            progress = min(t / effect_duration, 1.0)
            x = canvas_width - (canvas_width - center_x) * progress
            return (x, center_y)
        return text_clip.with_position(_pos), True
    elif name == "slide_top":
        def _pos(t: float) -> tuple[float, float]:
            progress = min(t / effect_duration, 1.0)
            y = -clip_h + (center_y + clip_h) * progress
            return (center_x, y)
        return text_clip.with_position(_pos), True
    elif name == "slide_bottom":
        def _pos(t: float) -> tuple[float, float]:
            progress = min(t / effect_duration, 1.0)
            y = canvas_height - (canvas_height - center_y) * progress
            return (center_x, y)
        return text_clip.with_position(_pos), True

    return text_clip, False


def _caption_box_size(size: CanvasSize, settings: RenderSettings) -> tuple[int, int]:
    return (
        max(1, size.width - settings.text_margin_x * 2),
        max(1, size.height - settings.text_margin_y * 2),
    )


def _build_caption_text_clip(
    *,
    text: str,
    color: str,
    box_size: tuple[int, int],
    settings: RenderSettings,
    duration: float,
    text_align: str = "center",
    horizontal_align: str = "center",
    font_size: int | None = None,
) -> TextClip:
    actual_font_size = font_size or settings.font_size
    return TextClip(
        font=str(settings.font_path),
        text=text,
        font_size=actual_font_size,
        color=color,
        bg_color=None,
        size=box_size,
        method="caption",
        text_align=text_align,
        horizontal_align=horizontal_align,
        vertical_align="center",
        interline=int(actual_font_size * (settings.line_spacing - 1)),
        transparent=True,
        duration=duration,
    )


def _ease_out_quad(progress: float) -> float:
    clamped = min(max(progress, 0.0), 1.0)
    return 1.0 - (1.0 - clamped) * (1.0 - clamped)


def _measure_text_width(text: str, font_path: Path, font_size: int) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    try:
        font = ImageFont.truetype(str(font_path), size=font_size)
        left, top, right, bottom = font.getbbox(cleaned)
        return max(0, right - left)
    except Exception:  # noqa: BLE001
        return 0


def _fit_single_line_font_size(
    *,
    text: str,
    font_path: Path,
    target_size: int,
    min_size: int,
    max_width: int,
) -> int:
    if max_width <= 0:
        return max(min_size, target_size)

    for candidate in range(target_size, min_size - 1, -1):
        if _measure_text_width(text, font_path, candidate) <= max_width:
            return candidate
    return min_size


def _build_lyrics_text_clips(
    *,
    item: AudioItem,
    sentences: list[str],
    size: CanvasSize,
    settings: RenderSettings,
    total_duration: float,
) -> list[TextClip]:
    clip_w, _ = _caption_box_size(size, settings)
    current_idx = item.index - 1
    current_text = item.text
    if 0 <= current_idx < len(sentences):
        current_text = sentences[current_idx]

    context_font_size = settings.font_size
    target_current_font_size = max(context_font_size + 2, int(round(context_font_size * LYRICS_CURRENT_SCALE)))
    fit_min_size = max(settings.min_font_size, 1)
    max_single_line_width = int(clip_w * LYRICS_CURRENT_MAX_WIDTH_RATIO)
    current_font_size = _fit_single_line_font_size(
        text=current_text,
        font_path=settings.font_path,
        target_size=target_current_font_size,
        min_size=fit_min_size,
        max_width=max_single_line_width,
    )

    layout_font_size = max(context_font_size, current_font_size)
    line_gap = max(1, int(layout_font_size * settings.line_spacing * 0.95))
    line_box_h = max(layout_font_size + 10, int(layout_font_size * settings.line_spacing * 1.4))
    line_box_size = (clip_w, line_box_h)
    center_x = (size.width - clip_w) / 2.0
    center_y = size.height / 2.0

    scroll_duration = min(0.45, total_duration * 0.35) if total_duration > 0 else 0.0
    should_scroll = current_idx > 0 and len(sentences) > 1 and scroll_duration > 0.0

    def _scroll_offset(t: float) -> float:
        if not should_scroll:
            return 0.0
        if t <= 0.0:
            return float(line_gap)
        if t >= scroll_duration:
            return 0.0
        progress = _ease_out_quad(t / scroll_duration)
        return float(line_gap) * (1.0 - progress)

    def _line_pos(base_center_y: float):
        def _pos(t: float) -> tuple[float, float]:
            y = base_center_y + _scroll_offset(t) - (line_box_h / 2.0)
            return (center_x, y)
        return _pos

    clips: list[TextClip] = []
    context_rows = max(1, (LYRICS_VISIBLE_LINES - 1) // 2)
    for rel in range(-context_rows, context_rows + 1):
        sentence_idx = current_idx + rel
        text = ""
        if 0 <= sentence_idx < len(sentences):
            text = sentences[sentence_idx]
        if not text.strip():
            continue
        row_center_y = center_y + rel * line_gap
        opacity = 1.0 if rel == 0 else LYRICS_CONTEXT_OPACITY
        row_font_size = current_font_size if rel == 0 else context_font_size
        clip = _build_caption_text_clip(
            text=text,
            color=settings.text_color,
            box_size=line_box_size,
            settings=settings,
            duration=total_duration,
            text_align="center",
            horizontal_align="center",
            font_size=row_font_size,
        ).with_position(_line_pos(row_center_y))
        if opacity < 1.0:
            clip = clip.with_opacity(opacity)
        clips.append(clip)
    return clips


def _create_single_clip(
    item: AudioItem,
    sentences: list[str],
    size: CanvasSize,
    settings: RenderSettings,
    clips_dir: Path,
    fps: int,
    tts_start_offset: float,
    logger: logging.Logger | None,
) -> tuple[int, Path]:
    clip_path = clips_dir / numbered_name(item.index, "mp4")

    last_exc: Exception | None = None
    for attempt in range(1, MAX_CLIP_RETRIES + 1):
        try:
            audio = AudioFileClip(str(item.audio_path))
            clip_delay = tts_start_offset if item.index == 1 else 0.0
            total_duration = audio.duration + clip_delay

            # Background: solid color filling the full canvas.
            bg = ColorClip(
                size=(size.width, size.height),
                color=_hex_to_rgb(settings.bg_color),
                duration=total_duration,
            ).with_fps(fps)

            text_layers: list[TextClip] = []
            if settings.caption_style == "lyrics":
                text_layers = _build_lyrics_text_clips(
                    item=item,
                    sentences=sentences,
                    size=size,
                    settings=settings,
                    total_duration=total_duration,
                )
            else:
                # Text clip: sentence rendered via MoviePy TextClip.
                text_color = _pick_text_color(item.index, settings)
                text = _build_caption_text_clip(
                    text=item.text,
                    color=text_color,
                    box_size=_caption_box_size(size, settings),
                    settings=settings,
                    duration=total_duration,
                )

                # Apply effect (cycling).
                effect_name = _pick_effect_name(item.index, settings)
                text, handles_position = _apply_text_effect(
                    text, effect_name, settings.effect_duration,
                    canvas_width=size.width, canvas_height=size.height,
                )

                # Compose text on background. If the effect already controls
                # the position (e.g. slide effects) we must not override it.
                if not handles_position:
                    text = text.with_position("center")
                text_layers = [text]

            video = CompositeVideoClip(
                [bg, *text_layers],
                size=(size.width, size.height),
            )

            if clip_delay > 0:
                silence = _silent_audio(clip_delay, fps=audio.fps or 44100)
                composite_audio = CompositeAudioClip([
                    silence.with_start(0),
                    audio.with_start(clip_delay),
                ]).with_duration(total_duration)
                video = video.with_audio(composite_audio)
            else:
                video = video.with_audio(audio)

            video.write_videofile(
                str(clip_path),
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                preset="superfast",
                threads=1,
                logger=None,
            )
            audio.close()
            video.close()

            if logger:
                logger.info("clip generated: %s", clip_path)
            return item.index, clip_path.resolve()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if logger:
                logger.warning(
                    "clip generation failed #%03d attempt=%d/%d: %s",
                    item.index,
                    attempt,
                    MAX_CLIP_RETRIES,
                    exc,
                )
            if clip_path.exists():
                clip_path.unlink()
            if attempt < MAX_CLIP_RETRIES:
                time.sleep(float(attempt))

    raise RuntimeError(
        f"Failed to generate clip after {MAX_CLIP_RETRIES} attempts: {clip_path}"
    ) from last_exc


def create_clips_for_mode(
    audio_items: list[AudioItem],
    sentences: list[str],
    size: CanvasSize,
    settings: RenderSettings,
    clips_dir: Path,
    fps: int,
    tts_start_offset: float = 1.0,
    logger: logging.Logger | None = None,
    max_workers: int | None = None,
) -> list[Path]:
    clips_dir.mkdir(parents=True, exist_ok=True)
    workers = max_workers or _default_clip_workers()
    if workers <= 0:
        raise ValueError("max_workers for clip generation must be > 0")

    if len(audio_items) <= 1 or workers == 1:
        ordered: dict[int, Path] = {}
        for item in audio_items:
            index, path = _create_single_clip(
                item=item,
                sentences=sentences,
                size=size,
                settings=settings,
                clips_dir=clips_dir,
                fps=fps,
                tts_start_offset=tts_start_offset,
                logger=logger,
            )
            ordered[index] = path
        return [ordered[index] for index in range(1, len(audio_items) + 1)]

    futures = {}
    ordered: dict[int, Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for item in audio_items:
            future = executor.submit(
                _create_single_clip,
                item,
                sentences,
                size,
                settings,
                clips_dir,
                fps,
                tts_start_offset,
                logger,
            )
            futures[future] = item.index

        for future in as_completed(futures):
            index, path = future.result()
            ordered[index] = path

    return [ordered[index] for index in range(1, len(audio_items) + 1)]


def _concat_line(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def write_concat_file(
    mode: OutputMode,
    clips_dir: Path,
    concat_dir: Path,
    total_count: int,
    file_name: str | None = None,
) -> Path:
    concat_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index in range(1, total_count + 1):
        clip_path = clips_dir / numbered_name(index, "mp4")
        if not clip_path.exists():
            raise FileNotFoundError(f"Missing clip for concat: {clip_path}")
        lines.append(_concat_line(clip_path))
    concat_path = concat_dir / (file_name or f"{mode}.txt")
    concat_path.write_text("\n".join(lines), encoding="utf-8")
    return concat_path


def concat_mode_video(
    mode: OutputMode,
    concat_file: Path,
    output_path: Path,
    fps: int,
    logger: logging.Logger | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        run_cmd(cmd, logger=logger, check=True)
    except Exception as exc:
        raise RuntimeError(f"FFmpeg concat failed: {exc}") from exc

    if logger:
        logger.info("%s output generated: %s", mode, output_path)
    return output_path.resolve()


def overlay_cover_on_first_frame(
    *,
    video_path: Path,
    cover_path: Path,
    output_path: Path,
    fps: int,
    logger: logging.Logger | None = None,
) -> Path:
    if fps <= 0:
        raise ValueError("fps must be > 0 for first-frame cover overlay")

    frame_window = 1.0 / float(fps)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video = VideoFileClip(str(video_path))
    cover = ImageClip(str(cover_path)).with_duration(frame_window)

    final = CompositeVideoClip([video, cover])
    try:
        final.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="superfast",
            threads=1,
            logger=None,
        )
    finally:
        video.close()
        cover.close()
        final.close()

    if logger:
        logger.info("cover overlaid on first frame: %s", output_path)
    return output_path.resolve()
