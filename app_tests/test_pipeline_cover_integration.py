from __future__ import annotations

import json
from pathlib import Path

import pipeline_main
from models import AudioItem


def _build_args(tmp_path: Path, *, cover_enabled: bool = True):
    font_file = tmp_path / "font.ttf"
    font_file.write_bytes(b"dummy")

    parser = pipeline_main._build_parser()
    raw = parser.parse_args(
        [
            "--text",
            "第一句。第二句。",
            "--font-path",
            str(font_file),
            "--work-dir",
            str(tmp_path / "out"),
            "--output-modes",
            "portrait,landscape",
            "--cover-enabled",
            "true" if cover_enabled else "false",
        ]
    )
    return pipeline_main._merge_args(raw)


def test_run_cover_overlay_called_for_both_modes(monkeypatch, tmp_path: Path) -> None:
    args = _build_args(tmp_path, cover_enabled=True)

    monkeypatch.setattr(pipeline_main, "ensure_ffmpeg_tools", lambda: None)
    monkeypatch.setattr(pipeline_main, "split_sentences", lambda _text: ["第一句。", "第二句。"])

    def fake_generate_tts(*, sentences, audio_dir, voice, rate, volume, logger, max_workers):
        audio_dir.mkdir(parents=True, exist_ok=True)
        items = []
        for idx, text in enumerate(sentences, start=1):
            audio_path = audio_dir / f"{idx:04d}.mp3"
            audio_path.write_bytes(b"audio")
            items.append(AudioItem(index=idx, text=text, audio_path=audio_path, duration=1.0))
        return items

    monkeypatch.setattr(pipeline_main, "generate_tts", fake_generate_tts)

    def fake_render_cover_image(*, mode, size, settings, theme_keyword, font_path, out_dir, logger):
        p = out_dir / "0000_cover.png"
        p.write_bytes(b"cover")
        return p

    monkeypatch.setattr(pipeline_main, "render_cover_image", fake_render_cover_image)

    cover_calls: list[str] = []

    def fake_create_clips_for_mode(*, audio_items, sentences, size, settings, clips_dir, fps, tts_start_offset, logger, max_workers):
        clips_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        for item in audio_items:
            p = clips_dir / f"{item.index:04d}.mp4"
            p.write_bytes(b"clip")
            outputs.append(p)
        return outputs

    monkeypatch.setattr(pipeline_main, "create_clips_for_mode", fake_create_clips_for_mode)

    def fake_write_concat_file(*, mode, clips_dir, concat_dir, total_count, file_name):
        concat_dir.mkdir(parents=True, exist_ok=True)
        p = concat_dir / file_name
        p.write_text("file 'dummy'", encoding="utf-8")
        return p

    monkeypatch.setattr(pipeline_main, "write_concat_file", fake_write_concat_file)

    def fake_concat_mode_video(*, mode, concat_file, output_path, fps, logger):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"raw")
        return output_path

    monkeypatch.setattr(pipeline_main, "concat_mode_video", fake_concat_mode_video)

    def fake_overlay_cover_on_first_frame(*, video_path, cover_path, output_path, fps, logger):
        cover_calls.append(output_path.name)
        output_path.write_bytes(b"covered")
        return output_path

    monkeypatch.setattr(pipeline_main, "overlay_cover_on_first_frame", fake_overlay_cover_on_first_frame)

    outputs = pipeline_main.run(args)

    assert len(outputs) == 2
    assert sorted(cover_calls) == ["cover_0001.mp4", "cover_0001.mp4"]


def test_run_cover_overlay_skipped_when_disabled(monkeypatch, tmp_path: Path) -> None:
    args = _build_args(tmp_path, cover_enabled=False)

    monkeypatch.setattr(pipeline_main, "ensure_ffmpeg_tools", lambda: None)
    monkeypatch.setattr(pipeline_main, "split_sentences", lambda _text: ["第一句。"])

    monkeypatch.setattr(
        pipeline_main,
        "generate_tts",
        lambda **kwargs: [
            AudioItem(index=1, text="第一句。", audio_path=Path(kwargs["audio_dir"]) / "0001.mp3", duration=1.0)
        ],
    )

    monkeypatch.setattr(
        pipeline_main,
        "render_cover_image",
        lambda **kwargs: Path(kwargs["out_dir"]) / "0000_cover.png",
    )
    monkeypatch.setattr(
        pipeline_main,
        "create_clips_for_mode",
        lambda **kwargs: [Path(kwargs["clips_dir"]) / "0001.mp4"],
    )
    monkeypatch.setattr(
        pipeline_main,
        "write_concat_file",
        lambda **kwargs: Path(kwargs["concat_dir"]) / kwargs["file_name"],
    )

    def fake_concat_mode_video(*, mode, concat_file, output_path, fps, logger):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"raw")
        return output_path

    monkeypatch.setattr(pipeline_main, "concat_mode_video", fake_concat_mode_video)

    called = {"overlay": False}

    def fake_overlay_cover_on_first_frame(**kwargs):
        called["overlay"] = True
        return kwargs["output_path"]

    monkeypatch.setattr(pipeline_main, "overlay_cover_on_first_frame", fake_overlay_cover_on_first_frame)

    outputs = pipeline_main.run(args)

    assert len(outputs) == 2
    assert called["overlay"] is False
