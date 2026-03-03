from __future__ import annotations

import functools
import logging
import os
import random
import re
import time
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
FLIP_OPEN_PUNCT = set("（([【《<“‘\"")
FLIP_CLOSE_PUNCT = FLIP_PUNCT - FLIP_OPEN_PUNCT
FLIP_WORD_CONNECTOR = {"-", "'", "."}


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
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF      # CJK Unified Ideographs
        or 0x3400 <= code <= 0x4DBF   # CJK Extension A
        or 0xF900 <= code <= 0xFAFF   # CJK Compatibility Ideographs
    )


def _is_alnum_char(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


@functools.lru_cache(maxsize=1)
def _load_jieba_module():
    try:
        import jieba  # type: ignore[import-not-found]
    except Exception:
        return None
    return jieba


def _split_cjk_phrase(text: str) -> list[str]:
    if not text:
        return []

    jieba_module = _load_jieba_module()
    if jieba_module is not None:
        try:
            words = [word.strip() for word in jieba_module.cut(text, HMM=False) if word.strip()]
            if words:
                return words
        except Exception:
            pass

    # Fallback: keep mostly two-char chunks while avoiding 1-char tail tokens.
    words: list[str] = []
    i = 0
    while i < len(text):
        remaining = len(text) - i
        if remaining <= 2:
            words.append(text[i:])
            break
        if remaining == 3:
            words.append(text[i:])
            break
        words.append(text[i:i + 2])
        i += 2
    return [word for word in words if word]


def _merge_flip_punct(tokens: list[str]) -> list[str]:
    if not tokens:
        return []

    merged: list[str] = []
    pending_prefix = ""
    for token in tokens:
        if token in FLIP_OPEN_PUNCT:
            pending_prefix += token
            continue
        if token in FLIP_CLOSE_PUNCT:
            if merged:
                merged[-1] = f"{merged[-1]}{token}"
            elif pending_prefix:
                pending_prefix += token
            else:
                merged.append(token)
            continue

        if pending_prefix:
            token = f"{pending_prefix}{token}"
            pending_prefix = ""
        merged.append(token)

    if pending_prefix:
        if merged:
            merged[-1] = f"{merged[-1]}{pending_prefix}"
        else:
            merged.append(pending_prefix)
    return [token for token in merged if token]


def _tokenize_flip_big_words(text: str) -> list[str]:
    raw_tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue

        if _is_cjk_char(ch):
            j = i + 1
            while j < n and _is_cjk_char(text[j]):
                j += 1
            raw_tokens.extend(_split_cjk_phrase(text[i:j]))
            i = j
            continue

        if _is_alnum_char(ch):
            token_chars = [ch]
            i += 1
            while i < n:
                nxt = text[i]
                if _is_alnum_char(nxt):
                    token_chars.append(nxt)
                    i += 1
                    continue
                if (
                    nxt in FLIP_WORD_CONNECTOR
                    and i + 1 < n
                    and _is_alnum_char(token_chars[-1])
                    and _is_alnum_char(text[i + 1])
                ):
                    token_chars.append(nxt)
                    token_chars.append(text[i + 1])
                    i += 2
                    continue
                break
            raw_tokens.append("".join(token_chars))
            continue

        raw_tokens.append(ch)
        i += 1

    return _merge_flip_punct(raw_tokens)


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


def _needs_space_between_tokens(prev_token: str, next_token: str) -> bool:
    if not prev_token or not next_token:
        return False
    prev_last = prev_token[-1]
    next_first = next_token[0]
    return (
        prev_last.isascii()
        and next_first.isascii()
        and prev_last.isalnum()
        and next_first.isalnum()
    )


def _join_flip_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""
    parts = [tokens[0]]
    for token in tokens[1:]:
        if _needs_space_between_tokens(parts[-1], token):
            parts.append(" ")
        parts.append(token)
    return "".join(parts)


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
        candidate = _join_flip_tokens(current_line + [token])
        if (not current_line) or _measure_text_width(candidate, font_path, font_size) <= max_width:
            current_line.append(token)
            continue
        lines.append(current_line)
        current_line = [token]
    if current_line:
        lines.append(current_line)
    return lines


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


def _flip_big_anchor_y(size: CanvasSize, settings: RenderSettings, *, sentence_mode: bool) -> float:
    ratio = (
        settings.flip_big_sentence_anchor_y_ratio
        if sentence_mode
        else settings.flip_big_anchor_y_ratio
    )
    ratio = max(0.0, min(1.0, float(ratio)))
    top_bound = float(settings.text_margin_y)
    bottom_bound = float(max(settings.text_margin_y, size.height - settings.text_margin_y))
    anchor = float(size.height) * ratio
    return min(max(anchor, top_bound), bottom_bound)


def _progressive_time_windows(
    tokens: list[str],
    duration: float,
    settings: RenderSettings,
) -> list[tuple[float, float]]:
    if not tokens:
        return []

    min_weight = max(2.0, settings.font_size * 0.08)
    weights = [
        max(min_weight, _measure_text_width(token, settings.font_path, settings.font_size))
        for token in tokens
    ]
    total_weight = sum(weights)
    if total_weight <= 0:
        step = duration / float(len(tokens))
        return [
            (idx * step, duration if idx == len(tokens) - 1 else (idx + 1) * step)
            for idx in range(len(tokens))
        ]

    windows: list[tuple[float, float]] = []
    cursor = 0.0
    for index, weight in enumerate(weights):
        start = duration * (cursor / total_weight)
        cursor += weight
        end = duration if index == len(tokens) - 1 else duration * (cursor / total_weight)
        if end <= start:
            end = min(duration, start + 0.001)
        windows.append((start, end))
    return windows


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


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000.0)))
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    sec = total_seconds % 60
    total_minutes = total_seconds // 60
    minute = total_minutes % 60
    hour = total_minutes // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def _format_ass_timestamp(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100.0)))
    cs = total_cs % 100
    total_seconds = total_cs // 100
    sec = total_seconds % 60
    total_minutes = total_seconds // 60
    minute = total_minutes % 60
    hour = total_minutes // 60
    return f"{hour:d}:{minute:02d}:{sec:02d}.{cs:02d}"


def _hex_to_ass_primary(hex_color: str) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _ass_alpha_from_opacity(opacity: float) -> str:
    clamped = max(0.0, min(1.0, opacity))
    alpha = int(round((1.0 - clamped) * 255.0))
    return f"&H{alpha:02X}&"


def _escape_ass_text(text: str) -> str:
    escaped = text.replace("\\", r"\\")
    escaped = escaped.replace("{", r"\{").replace("}", r"\}")
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
    return escaped.replace("\n", r"\N")


def _font_family_from_path(font_path: Path) -> str:
    mapping = {
        "msyh": "Microsoft YaHei",
        "msyhbd": "Microsoft YaHei",
        "simhei": "SimHei",
        "simsun": "SimSun",
        "arial": "Arial",
    }
    family = mapping.get(font_path.stem.lower(), font_path.stem)
    return family.replace(",", "")


def _build_flip_big_srt_events(
    item: AudioItem,
    size: CanvasSize,
    settings: RenderSettings,
    total_duration: float,
) -> list[tuple[float, float, str]]:
    duration = max(0.001, total_duration)
    if settings.flip_big_style == "sentence":
        tokens = _tokenize_flip_big_words(item.text)
        if not tokens:
            tokens = [item.text] if item.text else [""]
        area_w = _flip_big_layout_width(size, settings)
        wrapped = _wrap_tokens_to_lines(tokens, area_w, settings.font_path, settings.font_size)
        if not wrapped:
            wrapped = _fallback_wrap_by_count(tokens, size)
        text = "\n".join(_join_flip_tokens(line) for line in wrapped if line).strip() or item.text
        return [(0.0, duration, text)]

    tokens = _tokenize_flip_big_words(item.text)
    if not tokens:
        tokens = [item.text] if item.text else [""]
    windows = _progressive_time_windows(tokens, duration, settings)
    if not windows:
        windows = [(0.0, duration)]

    events: list[tuple[float, float, str]] = []
    for index, (start, end) in enumerate(windows):
        visible = tokens[: index + 1][-settings.flip_big_max_lines :]
        text = "\n".join(visible).strip()
        if not text:
            text = item.text
        events.append((start, end, text))
    return events


def _build_flip_big_ass_events(
    item: AudioItem,
    size: CanvasSize,
    settings: RenderSettings,
    total_duration: float,
) -> list[str]:
    duration = max(0.001, total_duration)
    color = _hex_to_ass_primary(settings.text_color)
    center_x = int(round(size.width / 2.0))
    events: list[str] = []

    if settings.flip_big_style == "sentence":
        tokens = _tokenize_flip_big_words(item.text)
        if not tokens:
            tokens = [item.text] if item.text else [""]
        area_w = _flip_big_layout_width(size, settings)
        wrapped = _wrap_tokens_to_lines(tokens, area_w, settings.font_path, settings.font_size)
        if not wrapped:
            wrapped = _fallback_wrap_by_count(tokens, size)
        text = (
            r"\N".join(_escape_ass_text(_join_flip_tokens(line)) for line in wrapped if line).strip()
            or _escape_ass_text(item.text)
        )

        center_y = int(round(_flip_big_anchor_y(size, settings, sentence_mode=True)))
        burst_cs = max(1, int(round(min(0.16, max(0.05, duration * 0.35)) * 100.0)))
        tags = (
            rf"\an5\pos({center_x},{center_y})\fs{settings.font_size}\c{color}\1a{_ass_alpha_from_opacity(1.0)}"
            rf"\frx-10\fscx85\fscy85\t(0,{burst_cs},\frx0\fscx100\fscy100)"
        )
        events.append(
            "Dialogue: 0,"
            f"{_format_ass_timestamp(0.0)},{_format_ass_timestamp(duration)},Default,,0,0,0,,"
            f"{{{tags}}}{text}"
        )
        return events

    tokens = _tokenize_flip_big_words(item.text)
    if not tokens:
        tokens = [item.text] if item.text else [""]
    windows = _progressive_time_windows(tokens, duration, settings)
    if not windows:
        windows = [(0.0, duration)]
    token_count = max(1, len(windows))
    spin_events = _build_history_spin_events(token_count, seed_text=item.text)
    history_font_size = max(18, int(settings.font_size * 0.70))
    line_gap = max(6, int(settings.font_size * 0.10))
    top_bound = float(settings.text_margin_y)
    bottom_bound = float(max(settings.text_margin_y, size.height - settings.text_margin_y))
    available_height = max(1.0, bottom_bound - top_bound)
    anchor_y = _flip_big_anchor_y(size, settings, sentence_mode=False)

    for index, (start, end) in enumerate(windows):
        state_duration = max(0.001, end - start)
        visible_tokens = tokens[: index + 1][-settings.flip_big_max_lines :]
        has_spin = (index + 1) in spin_events
        spin_angle = int(spin_events[index + 1]) if has_spin else 0

        line_specs: list[tuple[str, bool, int, int]] = []
        for line_index, token in enumerate(visible_tokens):
            is_latest = line_index == len(visible_tokens) - 1
            font_size = settings.font_size if is_latest else history_font_size
            line_h = _font_line_height(settings.font_path, font_size, settings.line_spacing)
            line_specs.append((token, is_latest, font_size, line_h))

        block_height = sum(spec[3] for spec in line_specs)
        if len(line_specs) > 1:
            block_height += line_gap * (len(line_specs) - 1)
        if block_height >= available_height:
            block_top = top_bound
        else:
            block_top = max(top_bound, min(anchor_y - block_height / 2.0, bottom_bound - block_height))
        y_cursor = block_top

        for token, is_latest, font_size, line_h in line_specs:
            opacity = 1.0 if is_latest else (0.72 if has_spin else 0.85)
            alpha = _ass_alpha_from_opacity(opacity)
            y_pos = int(round(y_cursor + line_h / 2.0))

            tags = rf"\an5\pos({center_x},{y_pos})\fs{font_size}\c{color}\1a{alpha}"
            if is_latest:
                burst_cs = max(1, int(round(min(0.16, max(0.06, state_duration * 0.7)) * 100.0)))
                tags += rf"\frx-90\fscx90\fscy90\t(0,{burst_cs},\frx0\fscx100\fscy100)"
            elif has_spin:
                burst_cs = max(1, int(round(min(0.20, max(0.08, state_duration * 0.8)) * 100.0)))
                tags += rf"\frz0\t(0,{burst_cs},\frz{spin_angle})"

            line_text = _escape_ass_text(token)
            events.append(
                "Dialogue: 0,"
                f"{_format_ass_timestamp(start)},{_format_ass_timestamp(end)},Default,,0,0,0,,"
                f"{{{tags}}}{line_text}"
            )
            y_cursor += line_h + line_gap

    return events


def _build_flip_big_subtitles(
    item: AudioItem,
    size: CanvasSize,
    settings: RenderSettings,
    total_duration: float,
    clips_dir: Path,
) -> tuple[Path, Path]:
    srt_path = clips_dir / numbered_name(item.index, "srt")
    ass_path = clips_dir / numbered_name(item.index, "ass")

    srt_events = _build_flip_big_srt_events(item, size, settings, total_duration)
    srt_blocks: list[str] = []
    for idx, (start, end, text) in enumerate(srt_events, start=1):
        srt_blocks.append(str(idx))
        srt_blocks.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        srt_blocks.append(text.strip() or item.text)
        srt_blocks.append("")
    srt_path.write_text("\n".join(srt_blocks).rstrip() + "\n", encoding="utf-8")

    style_font = _font_family_from_path(settings.font_path)
    primary = _hex_to_ass_primary(settings.text_color)
    ass_header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {size.width}",
        f"PlayResY: {size.height}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,"
        f"{style_font},{settings.font_size},{primary},{primary},&H00000000,&H64000000,"
        f"0,0,0,0,100,100,0,0,1,2,0,8,10,10,{max(0, settings.text_margin_y)},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ass_events = _build_flip_big_ass_events(item, size, settings, total_duration)
    ass_path.write_text("\n".join(ass_header + ass_events) + "\n", encoding="utf-8")
    return srt_path.resolve(), ass_path.resolve()


def _escape_ffmpeg_filter_path(path: Path) -> str:
    escaped = path.resolve().as_posix()
    escaped = escaped.replace(":", r"\:")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace(",", r"\,")
    escaped = escaped.replace("[", r"\[").replace("]", r"\]")
    return escaped


def _burn_ass_subtitles(
    *,
    input_video: Path,
    ass_path: Path,
    output_video: Path,
    fps: int,
    logger: logging.Logger | None,
) -> Path:
    if fps <= 0:
        raise ValueError("fps must be > 0 for subtitle burning")

    ass_filter = _escape_ffmpeg_filter_path(ass_path)
    vf = f"ass='{ass_filter}'"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-vf",
        vf,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "superfast",
        "-c:a",
        "copy",
        str(output_video),
    ]
    run_cmd(cmd, logger=logger, check=True)
    return output_video.resolve()


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
    base_clip_path = clips_dir / numbered_name(item.index, "base.mp4")

    last_exc: Exception | None = None
    for attempt in range(1, MAX_CLIP_RETRIES + 1):
        audio: AudioFileClip | None = None
        video: CompositeVideoClip | None = None
        bg: ColorClip | None = None
        text: TextClip | None = None
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
                video = CompositeVideoClip([bg], size=(size.width, size.height))
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
                video = CompositeVideoClip([bg, text], size=(size.width, size.height))

            if clip_delay > 0:
                silence = _silent_audio(clip_delay, fps=audio.fps or 44100)
                composite_audio = CompositeAudioClip([
                    silence.with_start(0),
                    audio.with_start(clip_delay),
                ]).with_duration(total_duration)
                video = video.with_audio(composite_audio)
            else:
                video = video.with_audio(audio)

            render_target = base_clip_path if settings.subtitle_render_mode == "flip_big" else clip_path
            video.write_videofile(
                str(render_target),
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                preset="superfast",
                threads=1,
                logger=None,
            )

            if settings.subtitle_render_mode == "flip_big":
                _build_flip_big_subtitles(
                    item=item,
                    size=size,
                    settings=settings,
                    total_duration=total_duration,
                    clips_dir=clips_dir,
                )
                _burn_ass_subtitles(
                    input_video=base_clip_path,
                    ass_path=clips_dir / numbered_name(item.index, "ass"),
                    output_video=clip_path,
                    fps=fps,
                    logger=logger,
                )
                if base_clip_path.exists():
                    base_clip_path.unlink()

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
            if base_clip_path.exists():
                if attempt < MAX_CLIP_RETRIES:
                    base_clip_path.unlink()
                elif logger:
                    logger.warning("preserving temporary base clip for debugging: %s", base_clip_path)
            if attempt < MAX_CLIP_RETRIES:
                time.sleep(float(attempt))
        finally:
            if audio is not None:
                audio.close()
            if text is not None:
                text.close()
            if bg is not None:
                bg.close()
            if video is not None:
                video.close()

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
