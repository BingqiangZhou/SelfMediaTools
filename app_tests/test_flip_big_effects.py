from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops

import pipeline_main
import video
from models import AudioItem, CanvasSize, RenderSettings
from video import (
    _ass_alpha_from_opacity,
    _build_flip_big_ass_events,
    _build_flip_big_srt_events,
    _build_history_spin_events,
    _create_single_clip,
    _escape_ffmpeg_filter_path,
    _format_ass_timestamp,
    _format_srt_timestamp,
    _hex_to_ass_primary,
    _tokenize_flip_big_words,
)


def _run(cmd: list[str]) -> None:
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{completed.stderr}")


def _extract_pos_y(ass_line: str) -> int:
    match = re.search(r"\\pos\(\d+,(-?\d+)\)", ass_line)
    if not match:
        raise AssertionError(f"no ass pos() found: {ass_line}")
    return int(match.group(1))


def test_flip_big_defaults_and_cli_override(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"dummy")

    parser = pipeline_main._build_parser()
    raw_default = parser.parse_args(["--text", "hello", "--font-path", str(font_file)])
    merged_default = pipeline_main._merge_args(raw_default)
    assert merged_default.subtitle_render_mode == "classic"
    assert merged_default.flip_big_style == "progressive"
    assert merged_default.flip_big_max_lines == 3
    assert merged_default.flip_big_anchor_y_ratio == pytest.approx(0.56)
    assert merged_default.flip_big_sentence_anchor_y_ratio == pytest.approx(0.50)

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
            "--flip-big-anchor-y-ratio",
            "0.66",
            "--flip-big-sentence-anchor-y-ratio",
            "0.42",
        ]
    )
    merged_override = pipeline_main._merge_args(raw_override)
    assert merged_override.subtitle_render_mode == "flip_big"
    assert merged_override.flip_big_style == "sentence"
    assert merged_override.flip_big_max_lines == 5
    assert merged_override.flip_big_anchor_y_ratio == pytest.approx(0.66)
    assert merged_override.flip_big_sentence_anchor_y_ratio == pytest.approx(0.42)


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

    raw_bad_ratio = parser.parse_args(
        ["--text", "hello", "--font-path", str(font_file), "--flip-big-anchor-y-ratio", "1.2"]
    )
    with pytest.raises(ValueError, match="flip_big_anchor_y_ratio"):
        pipeline_main._validate_args(pipeline_main._merge_args(raw_bad_ratio))


def test_flip_big_helpers() -> None:
    tokens = _tokenize_flip_big_words("AI-powered tools don't fail, right?")
    assert tokens == ["AI-powered", "tools", "don't", "fail,", "right?"]

    punct_merged = _tokenize_flip_big_words("\u201c\u4f60\u597d\uff0c\u4e16\u754c\uff01\u201d\u8fd9\u662f\u6d4b\u8bd5\u3002")
    assert punct_merged[0].startswith("\u201c")
    assert punct_merged[-1].endswith("\u3002")
    assert all(token not in {"\u201c", "\u201d", "\uff0c", "\uff01", "\u3002"} for token in punct_merged)

    events = _build_history_spin_events(18, seed_text="abc")
    keys = sorted(events.keys())
    if keys:
        assert keys[0] >= 3
    for prev, cur in zip(keys, keys[1:]):
        assert 3 <= (cur - prev) <= 5
    for angle in events.values():
        assert angle in (-90.0, 90.0)

    assert _format_srt_timestamp(65.432) == "00:01:05,432"
    assert _format_ass_timestamp(65.432) == "0:01:05.43"
    assert _hex_to_ass_primary("#112233") == "&H00332211"
    assert _ass_alpha_from_opacity(1.0) == "&H00&"
    assert _ass_alpha_from_opacity(0.0) == "&HFF&"

    escaped = _escape_ffmpeg_filter_path(Path("C:/tmp/a b/test,1.ass"))
    assert r"\:" in escaped
    assert r"\," in escaped


def test_flip_big_progressive_timing_uses_token_widths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(video, "_tokenize_flip_big_words", lambda _text: ["A", "BBBB", "CC"])
    monkeypatch.setattr(
        video,
        "_measure_text_width",
        lambda token, _font_path, _font_size: {"A": 10.0, "BBBB": 40.0, "CC": 20.0}[token],
    )

    settings = RenderSettings(
        font_path=tmp_path / "dummy.ttf",
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
    item = AudioItem(index=1, text="ignored", audio_path=tmp_path / "a.wav", duration=7.0)
    events = _build_flip_big_srt_events(
        item=item,
        size=CanvasSize(width=720, height=1280),
        settings=settings,
        total_duration=7.0,
    )

    durations = [end - start for start, end, _ in events]
    assert len(durations) == 3
    assert durations[0] == pytest.approx(1.0, abs=0.02)
    assert durations[1] == pytest.approx(4.0, abs=0.02)
    assert durations[2] == pytest.approx(2.0, abs=0.02)


def test_flip_big_anchor_ratios_affect_position(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(video, "_tokenize_flip_big_words", lambda _text: ["one", "two"])
    monkeypatch.setattr(video, "_measure_text_width", lambda _token, _font, _size: 40.0)
    monkeypatch.setattr(video, "_font_line_height", lambda _font, _size, _spacing: 100)

    size = CanvasSize(width=720, height=1280)
    item = AudioItem(index=1, text="ignored", audio_path=tmp_path / "a.wav", duration=2.0)
    base_kwargs = dict(
        font_path=tmp_path / "dummy.ttf",
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
    low_settings = RenderSettings(**base_kwargs, flip_big_anchor_y_ratio=0.25)
    high_settings = RenderSettings(**base_kwargs, flip_big_anchor_y_ratio=0.75)

    low_events = _build_flip_big_ass_events(item=item, size=size, settings=low_settings, total_duration=2.0)
    high_events = _build_flip_big_ass_events(item=item, size=size, settings=high_settings, total_duration=2.0)
    assert _extract_pos_y(high_events[0]) > _extract_pos_y(low_events[0])

    sentence_low_kwargs = dict(base_kwargs)
    sentence_low_kwargs["flip_big_style"] = "sentence"
    sentence_low = RenderSettings(
        **sentence_low_kwargs,
        flip_big_sentence_anchor_y_ratio=0.20,
    )
    sentence_high_kwargs = dict(base_kwargs)
    sentence_high_kwargs["flip_big_style"] = "sentence"
    sentence_high = RenderSettings(
        **sentence_high_kwargs,
        flip_big_sentence_anchor_y_ratio=0.80,
    )
    sentence_low_events = _build_flip_big_ass_events(
        item=item, size=size, settings=sentence_low, total_duration=2.0
    )
    sentence_high_events = _build_flip_big_ass_events(
        item=item, size=size, settings=sentence_high, total_duration=2.0
    )
    assert _extract_pos_y(sentence_high_events[0]) > _extract_pos_y(sentence_low_events[0])


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

    item_progressive = AudioItem(
        index=1,
        text="\u54c8\u55bd\u5927\u5bb6\u597d\u6211\u662f\u6d4b\u8bd5\u6587\u672c",
        audio_path=audio_path,
        duration=2.0,
    )
    _, progressive_clip = _create_single_clip(
        item=item_progressive,
        size=size,
        settings=progressive_settings,
        clips_dir=clips_dir,
        fps=30,
        tts_start_offset=0.0,
        logger=None,
    )
    assert (clips_dir / "0001.srt").exists()
    assert (clips_dir / "0001.ass").exists()

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

    item_sentence = AudioItem(
        index=2,
        text="\u7ffb\u8f6c\u5927\u5b57\u6574\u53e5\u6a21\u5f0f",
        audio_path=audio_path,
        duration=2.0,
    )
    _, sentence_clip = _create_single_clip(
        item=item_sentence,
        size=size,
        settings=sentence_settings,
        clips_dir=clips_dir,
        fps=30,
        tts_start_offset=0.0,
        logger=None,
    )
    assert (clips_dir / "0002.srt").exists()
    assert (clips_dir / "0002.ass").exists()

    s0 = tmp_path / "sentence_start.png"
    s1 = tmp_path / "sentence_mid.png"
    _run(["ffmpeg", "-y", "-ss", "00:00:00.02", "-i", str(sentence_clip), "-frames:v", "1", str(s0)])
    _run(["ffmpeg", "-y", "-ss", "00:00:00.35", "-i", str(sentence_clip), "-frames:v", "1", str(s1)])

    with Image.open(s0) as im0, Image.open(s1) as im1:
        diff = ImageChops.difference(im0.convert("RGB"), im1.convert("RGB"))
        assert diff.getbbox() is not None
