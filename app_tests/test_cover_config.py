from __future__ import annotations

from pathlib import Path

import pipeline_main


def _write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_cover_config_merge_and_cli_override(tmp_path: Path) -> None:
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
                "cover_enabled: false",
                "cover_bg_color: \"#010203\"",
                "cover_text_color: \"#AA0000\"",
                "caption_style: lyrics",
            ]
        ),
    )

    parser = pipeline_main._build_parser()
    raw = parser.parse_args(
        [
            "--config",
            str(config),
            "--cover-enabled",
            "true",
            "--theme-keyword",
            "新关键词",
            "--caption-style",
            "classic",
        ]
    )
    merged = pipeline_main._merge_args(raw)

    assert merged.cover_enabled is True
    assert merged.theme_keyword == "新关键词"
    assert merged.cover_bg_color == "#010203"
    assert merged.cover_text_color == "#AA0000"
    assert merged.caption_style == "classic"


def test_theme_keyword_fallback() -> None:
    assert pipeline_main._resolve_theme_keyword(None) == "天命之人"
    assert pipeline_main._resolve_theme_keyword("   ") == "天命之人"
    assert pipeline_main._resolve_theme_keyword("成长") == "成长"


def test_work_dir_keeps_cwd_relative_when_loaded_from_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    font_file = tmp_path / "font.ttf"
    text_file = tmp_path / "input.txt"
    font_file.write_bytes(b"dummy")
    text_file.write_text("hello", encoding="utf-8")

    config = config_dir / "config.yaml"
    _write_config(
        config,
        "\n".join(
            [
                f"text_file: {text_file}",
                f"font_path: {font_file}",
                "work_dir: output",
            ]
        ),
    )

    parser = pipeline_main._build_parser()
    raw = parser.parse_args(["--config", str(config)])
    merged = pipeline_main._merge_args(raw)

    assert merged.work_dir == "output"
