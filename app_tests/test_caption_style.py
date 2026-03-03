from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops

import main
from models import AudioItem, CanvasSize, RenderSettings
from video import _create_single_clip


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


def _run(cmd: list[str]) -> None:
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{completed.stderr}")


def _write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_caption_style_default_is_classic(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"dummy")

    parser = main._build_parser()
    raw = parser.parse_args(["--text", "hello", "--font-path", str(font_file)])
    merged = main._merge_args(raw)
    assert merged.caption_style == "classic"


def test_caption_style_config_and_cli_override(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    text_file = tmp_path / "input.txt"
    font_file.write_bytes(b"dummy")
    text_file.write_text("hello", encoding="utf-8")

    config = tmp_path / "config.yaml"
    _write_config(
        config,
        "\n".join(
            [
                f"text_file: {text_file.name}",
                f"font_path: {font_file.name}",
                "caption_style: lyrics",
            ]
        ),
    )

    parser = main._build_parser()
    raw = parser.parse_args(["--config", str(config)])
    merged = main._merge_args(raw)
    assert merged.caption_style == "lyrics"

    raw_override = parser.parse_args(["--config", str(config), "--caption-style", "classic"])
    merged_override = main._merge_args(raw_override)
    assert merged_override.caption_style == "classic"


def test_caption_style_invalid_value_raises(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"dummy")

    parser = main._build_parser()
    raw = parser.parse_args(
        [
            "--text",
            "hello",
            "--font-path",
            str(font_file),
            "--caption-style",
            "invalid",
        ]
    )
    merged = main._merge_args(raw)

    with pytest.raises(ValueError, match="caption_style must be one of"):
        main._validate_args(merged)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_lyrics_style_scroll_has_visual_change(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "silent.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2", str(audio_path)])

    font_path = _find_font()
    settings = RenderSettings(
        font_path=font_path,
        font_size=56,
        min_font_size=20,
        line_spacing=1.25,
        text_margin_x=40,
        text_margin_y=40,
        bg_color="#000000",
        text_color="#FFFFFF",
        text_colors=(),
        text_effects=("slide_left",),
        effect_duration=0.8,
        use_text_effects=True,
        random_color=True,
        random_effect=True,
        caption_style="lyrics",
    )
    sentences = ["Line one for lyrics test.", "Line two is highlighted.", "Line three is next."]
    item = AudioItem(index=2, text=sentences[1], audio_path=audio_path, duration=2.0)

    _, out_path = _create_single_clip(
        item=item,
        sentences=sentences,
        size=CanvasSize(width=720, height=1280),
        settings=settings,
        clips_dir=clips_dir,
        fps=30,
        tts_start_offset=0.0,
        logger=None,
    )
    assert out_path.exists()

    frame0 = tmp_path / "lyrics_t0.png"
    frame1 = tmp_path / "lyrics_t05.png"
    _run(["ffmpeg", "-y", "-ss", "00:00:00", "-i", str(out_path), "-frames:v", "1", str(frame0)])
    _run(["ffmpeg", "-y", "-ss", "00:00:00.50", "-i", str(out_path), "-frames:v", "1", str(frame1)])

    with Image.open(frame0) as f0, Image.open(frame1) as f1:
        diff = ImageChops.difference(f0, f1)
        assert diff.getbbox() is not None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_lyrics_style_does_not_call_classic_effects(monkeypatch, tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "silent.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(audio_path)])

    font_path = _find_font()
    settings = RenderSettings(
        font_path=font_path,
        font_size=48,
        min_font_size=20,
        line_spacing=1.25,
        text_margin_x=40,
        text_margin_y=40,
        bg_color="#000000",
        text_color="#FFFFFF",
        text_colors=("#FFD700",),
        text_effects=("slide_left",),
        effect_duration=0.8,
        use_text_effects=True,
        random_color=True,
        random_effect=True,
        caption_style="lyrics",
    )
    item = AudioItem(index=2, text="Line two", audio_path=audio_path, duration=1.0)
    sentences = ["Line one", "Line two", "Line three"]

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("_apply_text_effect should not be called in lyrics mode")

    monkeypatch.setattr("video._apply_text_effect", _raise_if_called)

    _, out_path = _create_single_clip(
        item=item,
        sentences=sentences,
        size=CanvasSize(width=640, height=360),
        settings=settings,
        clips_dir=clips_dir,
        fps=30,
        tts_start_offset=0.0,
        logger=None,
    )
    assert out_path.exists()
