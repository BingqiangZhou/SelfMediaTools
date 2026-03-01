from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


OutputMode = Literal["portrait", "landscape"]


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
    overlay_height_ratio: float
    overlay_box_width_ratio: float
    overlay_fit: Literal["cover", "contain"]
    overlay_top_margin: int
    overlay_text_gap: int


@dataclass(frozen=True)
class CoverSettings:
    prefix_text: str
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
