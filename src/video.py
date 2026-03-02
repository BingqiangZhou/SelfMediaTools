from __future__ import annotations

import logging
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)
from moviepy.audio.AudioClip import AudioClip

from models import AudioItem, CanvasSize, OutputMode, RenderSettings, numbered_name

MAX_CLIP_RETRIES = 3

# Supported text effect names for cycling.
SUPPORTED_EFFECTS = ("fadein", "fadeout", "slide_left", "slide_right", "slide_top", "slide_bottom", "rotate")


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


def _pick_text_color(index: int, settings: RenderSettings) -> str:
    """Pick text color by cycling through text_colors, falling back to text_color."""
    if settings.text_colors:
        return settings.text_colors[(index - 1) % len(settings.text_colors)]
    return settings.text_color


def _pick_effect_name(index: int, settings: RenderSettings) -> str | None:
    """Pick an effect name by cycling through text_effects."""
    if not settings.text_effects:
        return None
    return settings.text_effects[(index - 1) % len(settings.text_effects)]


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


def _create_single_clip(
    item: AudioItem,
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

            # Text clip: sentence rendered via MoviePy TextClip.
            text_color = _pick_text_color(item.index, settings)
            text = TextClip(
                font=str(settings.font_path),
                text=item.text,
                font_size=settings.font_size,
                color=text_color,
                bg_color=None,
                size=(size.width - settings.text_margin_x * 2, size.height - settings.text_margin_y * 2),
                method="caption",
                text_align="center",
                horizontal_align="center",
                vertical_align="center",
                interline=int(settings.font_size * (settings.line_spacing - 1)),
                transparent=True,
                duration=total_duration,
            )

            # Apply effect (cycling).
            effect_name = _pick_effect_name(item.index, settings)
            text, handles_position = _apply_text_effect(
                text, effect_name, settings.effect_duration,
                canvas_width=size.width, canvas_height=size.height,
            )

            # Compose text on background.  If the effect already controls
            # the position (e.g. slide effects) we must not override it.
            if not handles_position:
                text = text.with_position("center")

            video = CompositeVideoClip(
                [bg, text],
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

    # Parse the concat file to get the list of clip paths
    clip_paths: list[str] = []
    for line in concat_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("file '") and line.endswith("'"):
            path_str = line[6:-1].replace("'\\'", "'")
            clip_paths.append(path_str)

    if not clip_paths:
        raise ValueError(f"No clips found in concat file: {concat_file}")

    clips = []
    for p in clip_paths:
        clip = VideoFileClip(p)
        # Trim a tiny epsilon to avoid reading past the last frame
        safe_duration = clip.duration - 1.0 / fps
        if safe_duration > 0:
            clip = clip.subclipped(0, safe_duration)
        clips.append(clip)

    try:
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
    finally:
        for clip in clips:
            clip.close()
        try:
            final.close()
        except Exception:
            pass

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
            logger=None,
        )
    finally:
        video.close()
        cover.close()
        final.close()

    if logger:
        logger.info("cover overlaid on first frame: %s", output_path)
    return output_path.resolve()
