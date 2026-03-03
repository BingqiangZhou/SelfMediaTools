from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


OutputMode = Literal["portrait", "landscape"]
CaptionStyle = Literal["classic", "lyrics"]


@dataclass(frozen=True)
class CanvasSize:
    width: int
    height: int


@dataclass(frozen=True)
class RenderSettings:
    font_path: Path
    font_size: int
    min_font_size: int
    line_spacing: float
    text_margin_x: int
    text_margin_y: int
    bg_color: str
    text_color: str
    text_colors: tuple[str, ...] = ()
    text_effects: tuple[str, ...] = ()
    effect_duration: float = 0.5
    use_text_effects: bool = False
    random_color: bool = False
    random_effect: bool = False
    caption_style: CaptionStyle = "classic"


@dataclass(frozen=True)
class CoverSettings:
    bg_color: str
    text_color: str


@dataclass(frozen=True)
class AudioItem:
    index: int
    text: str
    audio_path: Path
    duration: float


def numbered_name(index: int, suffix: str) -> str:
    return f"{index:04d}.{suffix.lstrip('.')}"
