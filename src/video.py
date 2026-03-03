from __future__ import annotations

import functools
import logging
import os
import random
import re
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
    vfx,
)
from ffmpeg_utils import run_cmd
from moviepy.audio.AudioClip import AudioClip
from PIL import ImageFont

from models import AudioItem, CanvasSize, OutputMode, RenderSettings, numbered_name

MAX_CLIP_RETRIES = 3

# Supported text effect names for cycling.
SUPPORTED_EFFECTS = ("fadein", "fadeout", "slide_left", "slide_right", "slide_top", "slide_bottom", "rotate")
FLIP_PUNCT = set("，。！？；：,.!?;:、…（）()【】[]{}《》<>“”\"'‘’")


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


def _is_cjk_char(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _is_alnum_char(ch: str) -> bool:
    return bool(re.match(r"[A-Za-z0-9]", ch))


def _tokenize_flip_big_words(text: str) -> list[str]:
    raw_tokens: list[str] = []
    current: list[str] = []
    current_kind: str | None = None

    def _flush() -> None:
        nonlocal current_kind
        if current:
            raw_tokens.append("".join(current))
            current.clear()
        current_kind = None

    for ch in text:
        if ch.isspace():
            _flush()
            continue
        if ch in FLIP_PUNCT:
            _flush()
            raw_tokens.append(ch)
            continue
        if _is_cjk_char(ch):
            kind = "cjk"
        elif _is_alnum_char(ch):
            kind = "alnum"
        else:
            kind = "other"

        if current_kind is None or current_kind == kind:
            current.append(ch)
            current_kind = kind
            continue

        _flush()
        current.append(ch)
        current_kind = kind

    _flush()

    split_tokens: list[str] = []
    for token in raw_tokens:
        if token and all(_is_cjk_char(ch) for ch in token):
            for i in range(0, len(token), 2):
                split_tokens.append(token[i:i + 2])
            continue
        split_tokens.append(token)

    merged: list[str] = []
    for token in split_tokens:
        if token in FLIP_PUNCT and merged:
            merged[-1] = f"{merged[-1]}{token}"
        else:
            merged.append(token)

    return [token for token in merged if token]


@functools.lru_cache(maxsize=64)
def _load_font(font_path: str, font_size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, size=font_size)


def _measure_text_width(text: str, font_path: Path, font_size: int) -> float:
    if not text:
        return 0.0
    font = _load_font(str(font_path), font_size)
    if hasattr(font, "getlength"):
        return float(font.getlength(text))
    bbox = font.getbbox(text)
    return float(bbox[2] - bbox[0])


def _font_line_height(font_path: Path, font_size: int, line_spacing: float) -> int:
    font = _load_font(str(font_path), font_size)
    ascent, descent = font.getmetrics()
    return max(1, int((ascent + descent) * line_spacing))


def _wrap_tokens_to_lines(
    tokens: list[str],
    max_width: int,
    font_path: Path,
    font_size: int,
) -> list[list[str]]:
    if not tokens:
        return []

    lines: list[list[str]] = []
    current_line: list[str] = []
    for token in tokens:
        candidate = "".join(current_line + [token])
        if (not current_line) or _measure_text_width(candidate, font_path, font_size) <= max_width:
            current_line.append(token)
            continue
        lines.append(current_line)
        current_line = [token]
    if current_line:
        lines.append(current_line)
    return lines


def _clip_recent_lines(lines: list[list[str]], max_lines: int) -> list[list[str]]:
    if max_lines <= 0:
        return []
    if len(lines) <= max_lines:
        return lines
    return lines[-max_lines:]


def _flip_big_layout_width(size: CanvasSize, settings: RenderSettings) -> int:
    available = max(80, size.width - settings.text_margin_x * 2)
    ratio = 0.45 if size.width >= size.height else 0.78
    preferred = int(size.width * ratio)
    lower_bound = max(160, int(settings.font_size * 4.0))
    return max(lower_bound, min(available, preferred))


def _fallback_wrap_by_count(tokens: list[str], size: CanvasSize) -> list[list[str]]:
    if not tokens:
        return []
    max_per_line = 3 if size.width >= size.height else 4
    if len(tokens) <= max_per_line:
        return [tokens]
    return [tokens[i:i + max_per_line] for i in range(0, len(tokens), max_per_line)]


def _build_history_spin_events(token_count: int, seed_text: str) -> dict[int, float]:
    """Build spin events where key is 1-based token count and value is target angle."""
    if token_count <= 1:
        return {}

    rng = random.Random(seed_text)
    events: dict[int, float] = {}
    current = rng.randint(3, 5)
    while current <= token_count:
        events[current] = rng.choice((-90.0, 90.0))
        current += rng.randint(3, 5)
    return events


def _apply_flip_pulse(
    clip: TextClip | CompositeVideoClip,
    burst_duration: float,
    start_angle: float,
    start_scale: float,
) -> TextClip | CompositeVideoClip:
    if burst_duration <= 0:
        return clip

    def _rotation(t: float) -> float:
        if t >= burst_duration:
            return 0.0
        progress = t / burst_duration
        return start_angle * (1.0 - progress)

    def _scale(t: float) -> float:
        if t >= burst_duration:
            return 1.0
        progress = t / burst_duration
        eased = 1.0 - (1.0 - progress) * (1.0 - progress)
        return start_scale + (1.0 - start_scale) * eased

    return clip.with_effects([vfx.Resize(_scale), vfx.Rotate(_rotation, expand=False)])


def _apply_rotate_to_side(
    clip: TextClip | CompositeVideoClip,
    burst_duration: float,
    target_angle: float,
) -> TextClip | CompositeVideoClip:
    if burst_duration <= 0:
        return clip

    def _rotation(t: float) -> float:
        if t >= burst_duration:
            return target_angle
        progress = t / burst_duration
        return target_angle * progress

    return clip.with_effects([vfx.Rotate(_rotation, expand=False)])


def _build_flip_big_sentence_clip(
    item: AudioItem,
    size: CanvasSize,
    settings: RenderSettings,
    total_duration: float,
) -> TextClip:
    layout_width = _flip_big_layout_width(size, settings)
    text = TextClip(
        font=str(settings.font_path),
        text=item.text,
        font_size=settings.font_size,
        color=settings.text_color,
        bg_color=None,
        size=(layout_width, size.height - settings.text_margin_y * 2),
        method="caption",
        text_align="center",
        horizontal_align="center",
        vertical_align="center",
        interline=int(settings.font_size * (settings.line_spacing - 1)),
        transparent=True,
        duration=total_duration,
    ).with_position("center")
    burst = min(0.16, max(0.05, total_duration * 0.35))
    return _apply_flip_pulse(text, burst_duration=burst, start_angle=-10.0, start_scale=0.85)


def _build_flip_big_progressive_clip(
    item: AudioItem,
    size: CanvasSize,
    settings: RenderSettings,
    total_duration: float,
) -> CompositeVideoClip:
    area_w = _flip_big_layout_width(size, settings)
    area_h = max(50, size.height - settings.text_margin_y * 2)

    tokens = _tokenize_flip_big_words(item.text)
    if not tokens:
        tokens = [item.text] if item.text else [""]
    token_count = max(1, len(tokens))
    step = total_duration / float(token_count) if total_duration > 0 else 0.001

    big_font_size = settings.font_size
    history_font_size = max(18, int(settings.font_size * 0.70))
    line_gap = max(6, int(settings.font_size * 0.10))
    spin_events = _build_history_spin_events(token_count, seed_text=item.text)

    overlay_clips: list[CompositeVideoClip] = []
    for index in range(token_count):
        start = index * step
        state_duration = max(0.001, total_duration - start if index == token_count - 1 else step)
        active_tokens = tokens[: index + 1]
        visible_tokens = active_tokens[-settings.flip_big_max_lines :]

        state_layers: list[TextClip | CompositeVideoClip] = []
        y_cursor = 0.0
        for line_index, token in enumerate(visible_tokens):
            is_latest = line_index == len(visible_tokens) - 1
            font_size = big_font_size if is_latest else history_font_size
            line_clip = TextClip(
                font=str(settings.font_path),
                text=token,
                font_size=font_size,
                color=settings.text_color,
                bg_color=None,
                method="label",
                transparent=True,
                duration=state_duration,
            ).with_opacity(1.0 if is_latest else 0.85)
            if is_latest:
                # 90-degree entry rotation for the newest line.
                rotate_burst = min(0.16, max(0.06, state_duration * 0.7))
                line_clip = _apply_flip_pulse(
                    line_clip,
                    burst_duration=rotate_burst,
                    start_angle=-90.0,
                    start_scale=0.9,
                )
            elif (index + 1) in spin_events:
                # Every 3-5 phrases, historical lines spin to a random side (left/right).
                history_burst = min(0.20, max(0.08, state_duration * 0.8))
                line_clip = _apply_rotate_to_side(
                    line_clip,
                    burst_duration=history_burst,
                    target_angle=spin_events[index + 1],
                ).with_opacity(0.72)
            state_layers.append(line_clip.with_position((0, y_cursor)))
            line_height = _font_line_height(settings.font_path, font_size, settings.line_spacing)
            y_cursor += line_height + line_gap

        state_block = CompositeVideoClip(state_layers, size=(area_w, area_h)).with_duration(state_duration)
        burst = min(0.12, max(0.04, state_duration * 0.6))
        state_block = _apply_flip_pulse(state_block, burst_duration=burst, start_angle=-6.0, start_scale=0.92)
        block_x = (size.width - area_w) / 2.0
        overlay_clips.append(
            state_block.with_start(start).with_position((block_x, settings.text_margin_y))
        )

    return CompositeVideoClip(overlay_clips, size=(size.width, size.height)).with_duration(total_duration)


def _build_flip_big_text_layer(
    item: AudioItem,
    size: CanvasSize,
    settings: RenderSettings,
    total_duration: float,
) -> TextClip | CompositeVideoClip:
    if settings.flip_big_style == "sentence":
        return _build_flip_big_sentence_clip(item, size, settings, total_duration)
    return _build_flip_big_progressive_clip(item, size, settings, total_duration)


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

            if settings.subtitle_render_mode == "flip_big":
                if item.index == 1 and logger:
                    if settings.use_text_effects or settings.text_effects or settings.random_effect:
                        logger.info(
                            "subtitle_render_mode=flip_big: text_effects/use_text_effects/random_effect are ignored"
                        )
                    if settings.random_color:
                        logger.info("subtitle_render_mode=flip_big: random_color is ignored; text_color is used")
                text = _build_flip_big_text_layer(item, size, settings, total_duration)
            else:
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
