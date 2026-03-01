from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from models import CanvasSize, CoverSettings
from render_cards import render_cover_image


FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
]


def _find_font() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    pytest.skip("No CJK font found on test machine")


def test_render_cover_image_creates_expected_size(tmp_path: Path) -> None:
    font_path = _find_font()
    settings = CoverSettings(
        bg_color="#000000",
        text_color="#D00000",
    )

    output = render_cover_image(
        mode="portrait",
        size=CanvasSize(width=1080, height=1920),
        settings=settings,
        theme_keyword="天命之人",
        font_path=font_path,
        out_dir=tmp_path,
    )

    assert output.exists()
    with Image.open(output) as image:
        assert image.size == (1080, 1920)


def test_render_cover_image_handles_long_keyword(tmp_path: Path) -> None:
    font_path = _find_font()
    settings = CoverSettings(
        bg_color="#000000",
        text_color="#D00000",
    )

    output = render_cover_image(
        mode="landscape",
        size=CanvasSize(width=1920, height=1080),
        settings=settings,
        theme_keyword="这是一个非常非常长的主题关键词用于测试截断行为",
        font_path=font_path,
        out_dir=tmp_path,
    )

    assert output.exists()
