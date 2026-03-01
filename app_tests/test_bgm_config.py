from __future__ import annotations

from pathlib import Path

import pytest

import main


def _write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_nested_bgm_config_is_loaded_and_typed(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    bgm_file = tmp_path / "bgm.mp3"
    text_file = tmp_path / "input.txt"
    font_file.write_bytes(b"dummy")
    bgm_file.write_bytes(b"dummy")
    text_file.write_text("hello", encoding="utf-8")

    config = tmp_path / "config.yaml"
    _write_config(
        config,
        "\n".join(
            [
                f"text_file: {text_file.name}",
                f"font_path: {font_file.name}",
                "bgm:",
                "  enabled: true",
                f"  file: {bgm_file.name}",
                "  volume: 0.3",
                "  fade_in: 2.0",
                "  fade_out: 2.5",
                "  audio_bitrate: \"160k\"",
            ]
        ),
    )

    parser = main._build_parser()
    raw = parser.parse_args(["--config", str(config)])
    merged = main._merge_args(raw)

    assert merged.bgm_enabled is True
    assert Path(merged.bgm_file).resolve() == bgm_file.resolve()
    assert merged.bgm_volume == 0.3
    assert merged.bgm_fade_in == 2.0
    assert merged.bgm_fade_out == 2.5
    assert merged.bgm_audio_bitrate == "160k"


def test_bgm_enabled_without_file_raises(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"dummy")

    parser = main._build_parser()
    raw = parser.parse_args(
        [
            "--text",
            "hello",
            "--font-path",
            str(font_file),
            "--bgm-enabled",
            "true",
        ]
    )
    merged = main._merge_args(raw)

    with pytest.raises(ValueError, match="bgm_file is required"):
        main._validate_args(merged)


def test_cli_override_bgm_enabled_false(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    bgm_file = tmp_path / "bgm.mp3"
    font_file.write_bytes(b"dummy")
    bgm_file.write_bytes(b"dummy")

    config = tmp_path / "config.yaml"
    _write_config(
        config,
        "\n".join(
            [
                "text: hello",
                f"font_path: {font_file}",
                "bgm:",
                "  enabled: true",
                f"  file: {bgm_file}",
            ]
        ),
    )

    parser = main._build_parser()
    raw = parser.parse_args(
        ["--config", str(config), "--bgm-enabled", "false"]
    )
    merged = main._merge_args(raw)

    assert merged.bgm_enabled is False


def test_legacy_nested_config_is_mapped(tmp_path: Path) -> None:
    font_file = tmp_path / "font.ttf"
    text_file = tmp_path / "input.txt"
    font_file.write_bytes(b"dummy")
    text_file.write_text("hello", encoding="utf-8")

    config = tmp_path / "legacy.yaml"
    _write_config(
        config,
        "\n".join(
            [
                "input:",
                f"  file: {text_file.name}",
                "  text: null",
                "output:",
                "  root_dir: output_legacy",
                "image:",
                f"  font_path: {font_file.name}",
                "  width: 1080",
                "  height: 1920",
                "tts:",
                "  voice: zh-CN-XiaoxiaoNeural",
                "video:",
                "  fps: 30",
            ]
        ),
    )

    parser = main._build_parser()
    raw = parser.parse_args(["--config", str(config)])
    merged = main._merge_args(raw)

    assert Path(merged.text_file).resolve() == text_file.resolve()
    assert Path(merged.font_path).resolve() == font_file.resolve()
    assert merged.work_dir.endswith("output_legacy")
    assert merged.portrait_size == "1080x1920"
    assert merged.output_modes == "portrait,landscape"
