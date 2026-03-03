from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops

import pipeline_main
from models import AudioItem, CanvasSize, RenderSettings
from video import _build_history_spin_events, _clip_recent_lines, _create_single_clip, _tokenize_flip_big_words


def _run(cmd: list[str]) -> None:
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{completed.stderr}")


def test_flip_big_defaults_and_cli_override(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"dummy")

    parser = pipeline_main._build_parser()
    raw_default = parser.parse_args(["--text", "hello", "--font-path", str(font_file)])
    merged_default = pipeline_main._merge_args(raw_default)
    assert merged_default.subtitle_render_mode == "classic"
    assert merged_default.flip_big_style == "progressive"
    assert merged_default.flip_big_max_lines == 3

    raw_override = parser.parse_args(
        [
            "--text",
            "hello",
            "--font-path",
            str(font_file),
            "--subtitle-render-mode",
            "flip_big",
            "--flip-big-style",
            "sentence",
            "--flip-big-max-lines",
            "5",
        ]
    )
    merged_override = pipeline_main._merge_args(raw_override)
    assert merged_override.subtitle_render_mode == "flip_big"
    assert merged_override.flip_big_style == "sentence"
    assert merged_override.flip_big_max_lines == 5


def test_flip_big_invalid_config_values_raise(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    config_file = tmp_path / "config.yaml"
    font_file.write_bytes(b"dummy")
    config_file.write_text(
        "\n".join(
            [
                "text: hello",
                f"font_path: {font_file}",
                "subtitle_render_mode: bad_mode",
            ]
        ),
        encoding="utf-8",
    )

    parser = pipeline_main._build_parser()
    raw = parser.parse_args(["--config", str(config_file)])
    with pytest.raises(ValueError, match="subtitle_render_mode"):
        pipeline_main._merge_args(raw)


def test_flip_big_tokenization_and_overflow_helpers() -> None:
    tokens = _tokenize_flip_big_words("哈喽大家好！hello world,123")
    assert tokens == ["哈喽", "大家", "好！", "hello", "world,", "123"]

    lines = [["a"], ["b"], ["c"], ["d"], ["e"]]
    assert _clip_recent_lines(lines, 3) == [["c"], ["d"], ["e"]]

    events = _build_history_spin_events(18, seed_text="abc")
    keys = sorted(events.keys())
    if keys:
        assert keys[0] >= 3
    for prev, cur in zip(keys, keys[1:]):
        assert 3 <= (cur - prev) <= 5
    for angle in events.values():
        assert angle in (-90.0, 90.0)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_flip_big_progressive_and_sentence_render(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()

    audio_path = tmp_path / "silent.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2", str(audio_path)])

    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists():
        font_path = Path("C:/Windows/Fonts/simhei.ttf")

    size = CanvasSize(width=720, height=1280)

    progressive_settings = RenderSettings(
        font_path=font_path,
        font_size=72,
        min_font_size=28,
        line_spacing=1.25,
        text_margin_x=80,
        text_margin_y=120,
        bg_color="#000000",
        text_color="#FFFFFF",
        subtitle_render_mode="flip_big",
        flip_big_style="progressive",
        flip_big_max_lines=3,
    )
    sentence_settings = RenderSettings(
        font_path=font_path,
        font_size=72,
        min_font_size=28,
        line_spacing=1.25,
        text_margin_x=80,
        text_margin_y=120,
        bg_color="#000000",
        text_color="#FFFFFF",
        subtitle_render_mode="flip_big",
        flip_big_style="sentence",
        flip_big_max_lines=3,
    )

    item_progressive = AudioItem(index=1, text="哈喽大家好我是留白", audio_path=audio_path, duration=2.0)
    _, progressive_clip = _create_single_clip(
        item=item_progressive,
        size=size,
        settings=progressive_settings,
        clips_dir=clips_dir,
        fps=30,
        tts_start_offset=0.0,
        logger=None,
    )

    p0 = tmp_path / "progressive_early.png"
    p1 = tmp_path / "progressive_late.png"
    _run(["ffmpeg", "-y", "-ss", "00:00:00.15", "-i", str(progressive_clip), "-frames:v", "1", str(p0)])
    _run(["ffmpeg", "-y", "-ss", "00:00:01.60", "-i", str(progressive_clip), "-frames:v", "1", str(p1)])

    with Image.open(p0) as im0, Image.open(p1) as im1:
        diff = ImageChops.difference(im0.convert("RGB"), im1.convert("RGB"))
        assert diff.getbbox() is not None
        early_non_black = sum(1 for value in im0.convert("L").getdata() if value > 8)
        late_non_black = sum(1 for value in im1.convert("L").getdata() if value > 8)
        assert late_non_black > early_non_black

    item_sentence = AudioItem(index=2, text="翻转大字整句模式", audio_path=audio_path, duration=2.0)
    _, sentence_clip = _create_single_clip(
        item=item_sentence,
        size=size,
        settings=sentence_settings,
        clips_dir=clips_dir,
        fps=30,
        tts_start_offset=0.0,
        logger=None,
    )

    s0 = tmp_path / "sentence_start.png"
    s1 = tmp_path / "sentence_mid.png"
    _run(["ffmpeg", "-y", "-ss", "00:00:00.02", "-i", str(sentence_clip), "-frames:v", "1", str(s0)])
    _run(["ffmpeg", "-y", "-ss", "00:00:00.35", "-i", str(sentence_clip), "-frames:v", "1", str(s1)])

    with Image.open(s0) as im0, Image.open(s1) as im1:
        diff = ImageChops.difference(im0.convert("RGB"), im1.convert("RGB"))
        assert diff.getbbox() is not None
