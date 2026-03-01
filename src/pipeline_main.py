from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from bgm import mix_bgm
from ffmpeg_utils import ensure_ffmpeg_tools
from io_utils import parse_output_modes, parse_size, prepare_output_dirs, read_text_input
from models import CanvasSize, CoverSettings, OutputMode, RenderSettings
from render_cards import OverlayResolver, render_cover_image, render_images_for_mode
from text_split import split_sentences
from tts import generate_tts
from video import concat_mode_video, create_clips_for_mode, overlay_cover_on_first_frame, write_concat_file


DEFAULTS: dict[str, Any] = {
    "text": None,
    "text_file": None,
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+0%",
    "volume": "+0%",
    "tts_start_offset": 1.0,
    "output_modes": "portrait,landscape",
    "portrait_size": "1080x1920",
    "landscape_size": "1920x1080",
    "font_path": None,
    "font_size": 72,
    "min_font_size": 28,
    "line_spacing": 1.25,
    "text_margin_x": 80,
    "text_margin_y": 60,
    "bg_color": "#000000",
    "text_color": "#FFFFFF",
    "overlay_image": None,
    "overlay_dir": None,
    "overlay_height_ratio": 0.35,
    "overlay_box_width_ratio": 0.68,
    "overlay_fit": "cover",
    "overlay_top_margin": 48,
    "overlay_text_gap": 12,
    "fps": 30,
    "tts_workers": 4,
    "image_workers": 4,
    "clip_workers": 2,
    "work_dir": ".",
    "bgm_enabled": False,
    "bgm_file": None,
    "bgm_volume": 0.18,
    "bgm_fade_in": 1.5,
    "bgm_fade_out": 1.5,
    "bgm_audio_bitrate": "192k",
    "theme_keyword": None,
    "cover_enabled": True,
    "cover_prefix_text": "今日主题",
    "cover_bg_color": "#000000",
    "cover_text_color": "#D00000",
}
DEFAULT_THEME_KEYWORD = "天命之人"

CLI_KEYS = list(DEFAULTS.keys())
# Keep input/resource paths relative to config file, but keep work_dir relative to CWD.
PATH_KEYS = {"text_file", "font_path", "overlay_image", "overlay_dir", "bgm_file"}
WINDOWS_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def _parse_bool(raw: str) -> bool:
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid bool value: {raw}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Text -> sentence TTS -> sentence cards -> portrait/landscape videos"
    )
    parser.add_argument("--config", type=str, default=None, help="YAML config file path")

    parser.add_argument("--text", type=str, default=None, help="Input text content")
    parser.add_argument("--text-file", type=str, default=None, help="Input text file")

    parser.add_argument("--voice", type=str, default=None)
    parser.add_argument("--rate", type=str, default=None)
    parser.add_argument("--volume", type=str, default=None)
    parser.add_argument("--tts-start-offset", type=float, default=None)

    parser.add_argument("--output-modes", type=str, default=None)
    parser.add_argument("--portrait-size", type=str, default=None)
    parser.add_argument("--landscape-size", type=str, default=None)

    parser.add_argument("--font-path", type=str, default=None)
    parser.add_argument("--font-size", type=int, default=None)
    parser.add_argument("--min-font-size", type=int, default=None)
    parser.add_argument("--line-spacing", type=float, default=None)
    parser.add_argument("--text-margin-x", type=int, default=None)
    parser.add_argument("--text-margin-y", type=int, default=None)
    parser.add_argument("--bg-color", type=str, default=None)
    parser.add_argument("--text-color", type=str, default=None)

    parser.add_argument("--overlay-image", type=str, default=None)
    parser.add_argument("--overlay-dir", type=str, default=None)
    parser.add_argument("--overlay-height-ratio", type=float, default=None)
    parser.add_argument("--overlay-box-width-ratio", type=float, default=None)
    parser.add_argument("--overlay-fit", type=str, choices=["cover", "contain"], default=None)
    parser.add_argument("--overlay-top-margin", type=int, default=None)
    parser.add_argument("--overlay-text-gap", type=int, default=None)

    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--tts-workers", type=int, default=None)
    parser.add_argument("--image-workers", type=int, default=None)
    parser.add_argument("--clip-workers", type=int, default=None)
    parser.add_argument("--work-dir", type=str, default=None)

    parser.add_argument("--bgm-enabled", type=_parse_bool, default=None, metavar="true|false")
    parser.add_argument("--bgm-file", type=str, default=None)
    parser.add_argument("--bgm-volume", type=float, default=None)
    parser.add_argument("--bgm-fade-in", type=float, default=None)
    parser.add_argument("--bgm-fade-out", type=float, default=None)
    parser.add_argument("--bgm-audio-bitrate", type=str, default=None)

    parser.add_argument("--theme-keyword", type=str, default=None)
    parser.add_argument("--cover-enabled", type=_parse_bool, default=None, metavar="true|false")
    parser.add_argument("--cover-prefix-text", type=str, default=None)
    parser.add_argument("--cover-bg-color", type=str, default=None)
    parser.add_argument("--cover-text-color", type=str, default=None)
    return parser


def _build_logger(log_path: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(stream_handler)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(file_handler)

    return logger


def _resolve_config_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _flatten_config_dict(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        key_norm = key.replace("-", "_")
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                sub_key_norm = sub_key.replace("-", "_")
                normalized[f"{key_norm}_{sub_key_norm}"] = sub_value
        else:
            normalized[key_norm] = value
    return normalized


def _apply_legacy_aliases(normalized: dict[str, Any]) -> dict[str, Any]:
    mapped = dict(normalized)

    if "text" not in mapped and "input_text" in mapped:
        mapped["text"] = mapped.get("input_text")
    if "text_file" not in mapped and "input_file" in mapped:
        mapped["text_file"] = mapped.get("input_file")

    if "work_dir" not in mapped and "output_root_dir" in mapped:
        mapped["work_dir"] = mapped.get("output_root_dir")

    if "font_path" not in mapped and "image_font_path" in mapped:
        mapped["font_path"] = mapped.get("image_font_path")
    if "font_size" not in mapped and "image_font_size" in mapped:
        mapped["font_size"] = mapped.get("image_font_size")
    if "min_font_size" not in mapped and "image_min_font_size" in mapped:
        mapped["min_font_size"] = mapped.get("image_min_font_size")
    if "line_spacing" not in mapped and "image_line_spacing" in mapped:
        mapped["line_spacing"] = mapped.get("image_line_spacing")
    if "text_margin_x" not in mapped and "image_horizontal_padding" in mapped:
        mapped["text_margin_x"] = mapped.get("image_horizontal_padding")
    if "text_margin_y" not in mapped and "image_vertical_padding" in mapped:
        mapped["text_margin_y"] = mapped.get("image_vertical_padding")
    if "bg_color" not in mapped and "image_bg_color" in mapped:
        mapped["bg_color"] = mapped.get("image_bg_color")
    if "text_color" not in mapped and "image_text_color" in mapped:
        mapped["text_color"] = mapped.get("image_text_color")

    image_w = mapped.get("image_width")
    image_h = mapped.get("image_height")
    if image_w is not None and image_h is not None:
        if "portrait_size" not in mapped:
            mapped["portrait_size"] = f"{image_w}x{image_h}"

    if "voice" not in mapped and "tts_voice" in mapped:
        mapped["voice"] = mapped.get("tts_voice")
    if "rate" not in mapped and "tts_rate" in mapped:
        mapped["rate"] = mapped.get("tts_rate")
    if "volume" not in mapped and "tts_volume" in mapped:
        mapped["volume"] = mapped.get("tts_volume")
    if "fps" not in mapped and "video_fps" in mapped:
        mapped["fps"] = mapped.get("video_fps")

    return mapped


def _load_config(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Config file must be a YAML object (key-value map).")

    normalized = _apply_legacy_aliases(_flatten_config_dict(payload))

    for key in PATH_KEYS:
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            p = Path(value)
            if not p.is_absolute():
                p = (config_path.parent / p).resolve()
            normalized[key] = str(p)
    return normalized


def _try_fill_default_font(resolved: dict[str, Any]) -> None:
    if resolved.get("font_path"):
        return
    for candidate in WINDOWS_FONT_CANDIDATES:
        if Path(candidate).exists():
            resolved["font_path"] = candidate
            return


def _coerce_types(resolved: dict[str, Any]) -> None:
    for key in (
        "font_size",
        "min_font_size",
        "text_margin_x",
        "text_margin_y",
        "overlay_top_margin",
        "overlay_text_gap",
        "fps",
        "tts_workers",
        "image_workers",
        "clip_workers",
    ):
        resolved[key] = int(resolved[key])
    for key in (
        "line_spacing",
        "tts_start_offset",
        "overlay_height_ratio",
        "overlay_box_width_ratio",
        "bgm_volume",
        "bgm_fade_in",
        "bgm_fade_out",
    ):
        resolved[key] = float(resolved[key])

    if isinstance(resolved.get("bgm_enabled"), str):
        resolved["bgm_enabled"] = _parse_bool(str(resolved["bgm_enabled"]))
    else:
        resolved["bgm_enabled"] = bool(resolved.get("bgm_enabled", False))
    cover_enabled_value = resolved.get("cover_enabled", True)
    if isinstance(cover_enabled_value, str):
        resolved["cover_enabled"] = _parse_bool(str(cover_enabled_value))
    elif cover_enabled_value is None:
        resolved["cover_enabled"] = True
    else:
        resolved["cover_enabled"] = bool(cover_enabled_value)

    modes_value = resolved.get("output_modes")
    if isinstance(modes_value, list):
        resolved["output_modes"] = ",".join(str(item) for item in modes_value)
    elif not isinstance(modes_value, str):
        raise ValueError("output_modes must be a string like 'portrait,landscape' or a list.")

    fit_value = str(resolved.get("overlay_fit", "cover")).lower().strip()
    if fit_value not in {"cover", "contain"}:
        raise ValueError("overlay_fit must be 'cover' or 'contain'.")
    resolved["overlay_fit"] = fit_value

    bitrate_value = str(resolved.get("bgm_audio_bitrate", "")).strip()
    if not bitrate_value:
        raise ValueError("bgm_audio_bitrate must not be empty")
    resolved["bgm_audio_bitrate"] = bitrate_value

    prefix = str(resolved.get("cover_prefix_text", "") or "").strip()
    if not prefix:
        prefix = str(DEFAULTS["cover_prefix_text"])
    resolved["cover_prefix_text"] = prefix

    cover_bg = str(resolved.get("cover_bg_color", "") or "").strip()
    if not cover_bg:
        cover_bg = str(DEFAULTS["cover_bg_color"])
    resolved["cover_bg_color"] = cover_bg

    cover_text = str(resolved.get("cover_text_color", "") or "").strip()
    if not cover_text:
        cover_text = str(DEFAULTS["cover_text_color"])
    resolved["cover_text_color"] = cover_text


def _merge_args(raw_args: argparse.Namespace) -> argparse.Namespace:
    config_path = _resolve_config_path(raw_args.config)
    config_values = _load_config(config_path)

    resolved = dict(DEFAULTS)
    for key in CLI_KEYS:
        if key in config_values:
            resolved[key] = config_values[key]

    for key in CLI_KEYS:
        value = getattr(raw_args, key)
        if value is not None:
            resolved[key] = value

    _try_fill_default_font(resolved)
    _coerce_types(resolved)
    return argparse.Namespace(**resolved)


def _validate_args(args: argparse.Namespace) -> None:
    if not args.text and not args.text_file:
        raise ValueError("Either --text or --text-file must be provided (CLI or config).")
    if not args.font_path:
        raise ValueError("font_path is required (CLI --font-path or config font_path).")
    if args.font_size <= 0 or args.min_font_size <= 0:
        raise ValueError("font_size and min_font_size must be > 0")
    if args.min_font_size > args.font_size:
        raise ValueError("min_font_size must be <= font_size")
    if args.line_spacing <= 0:
        raise ValueError("line_spacing must be > 0")
    if args.tts_start_offset < 0:
        raise ValueError("tts_start_offset must be >= 0")
    if args.text_margin_x < 0 or args.text_margin_y < 0:
        raise ValueError("text_margin_x/text_margin_y must be >= 0")
    if args.fps <= 0:
        raise ValueError("fps must be > 0")
    if args.tts_workers <= 0 or args.image_workers <= 0 or args.clip_workers <= 0:
        raise ValueError("tts_workers/image_workers/clip_workers must be > 0")
    if not (0 <= args.overlay_height_ratio <= 1):
        raise ValueError("overlay_height_ratio must be between 0 and 1")
    if not (0 <= args.overlay_box_width_ratio <= 1):
        raise ValueError("overlay_box_width_ratio must be between 0 and 1")
    if args.overlay_top_margin < 0:
        raise ValueError("overlay_top_margin must be >= 0")
    if args.overlay_text_gap < 0:
        raise ValueError("overlay_text_gap must be >= 0")

    if args.bgm_volume < 0:
        raise ValueError("bgm_volume must be >= 0")
    if args.bgm_fade_in < 0 or args.bgm_fade_out < 0:
        raise ValueError("bgm_fade_in and bgm_fade_out must be >= 0")

    font_path = Path(args.font_path)
    if not font_path.exists():
        raise FileNotFoundError(
            f"Font path not found: {font_path}. Please provide a valid Chinese font file."
        )
    if args.overlay_image:
        overlay_image = Path(args.overlay_image)
        if not overlay_image.exists():
            raise FileNotFoundError(f"overlay_image not found: {overlay_image}")
    if args.overlay_dir:
        overlay_dir = Path(args.overlay_dir)
        if not overlay_dir.exists() or not overlay_dir.is_dir():
            raise FileNotFoundError(f"overlay_dir not found or not a directory: {overlay_dir}")

    if args.bgm_enabled:
        if not args.bgm_file:
            raise ValueError("bgm_file is required when bgm_enabled=true")
        bgm_path = Path(args.bgm_file)
        if not bgm_path.exists():
            raise FileNotFoundError(f"bgm_file not found: {bgm_path}")


def _mode_sizes(args: argparse.Namespace) -> dict[OutputMode, CanvasSize]:
    return {
        "portrait": parse_size(args.portrait_size, "portrait_size"),
        "landscape": parse_size(args.landscape_size, "landscape_size"),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _mode_dir(base_dir: Path, mode: OutputMode, is_multi_mode: bool) -> Path:
    if is_multi_mode:
        target = base_dir / mode
        target.mkdir(parents=True, exist_ok=True)
        return target
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _resolve_theme_keyword(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    if value:
        return value
    return DEFAULT_THEME_KEYWORD


def run(args: argparse.Namespace) -> list[Path]:
    _validate_args(args)
    ensure_ffmpeg_tools()

    modes = parse_output_modes(args.output_modes)
    is_multi_mode = len(modes) > 1
    root_dir = Path(args.work_dir).resolve()
    paths = prepare_output_dirs(root_dir)

    logger = _build_logger(paths["logs_dir"] / "pipeline.log")

    text = read_text_input(args.text, args.text_file)
    sentences = split_sentences(text)
    if not sentences:
        raise ValueError("No valid sentences after splitting.")
    logger.info("sentences: %d", len(sentences))

    sentence_manifest = [
        {"index": idx, "text": sentence, "length": len(sentence)}
        for idx, sentence in enumerate(sentences, start=1)
    ]
    _write_json(paths["sentences_dir"] / "sentences.json", sentence_manifest)

    audio_items = generate_tts(
        sentences=sentences,
        audio_dir=paths["audio_dir"],
        voice=args.voice,
        rate=args.rate,
        volume=args.volume,
        logger=logger,
        max_workers=args.tts_workers,
    )
    audio_manifest = [
        {
            "index": item.index,
            "text": item.text,
            "audio_path": str(item.audio_path),
            "duration": item.duration,
        }
        for item in audio_items
    ]
    _write_json(paths["audio_dir"] / "audio_manifest.json", audio_manifest)

    overlay_resolver = OverlayResolver(
        overlay_dir=Path(args.overlay_dir).resolve() if args.overlay_dir else None,
        fixed_image=Path(args.overlay_image).resolve() if args.overlay_image else None,
    )
    settings = RenderSettings(
        font_path=Path(args.font_path).resolve(),
        font_size=args.font_size,
        min_font_size=args.min_font_size,
        line_spacing=args.line_spacing,
        text_margin_x=args.text_margin_x,
        text_margin_y=args.text_margin_y,
        bg_color=args.bg_color,
        text_color=args.text_color,
        overlay_height_ratio=args.overlay_height_ratio,
        overlay_box_width_ratio=args.overlay_box_width_ratio,
        overlay_fit=args.overlay_fit,
        overlay_top_margin=args.overlay_top_margin,
        overlay_text_gap=args.overlay_text_gap,
    )
    cover_settings = CoverSettings(
        prefix_text=args.cover_prefix_text,
        bg_color=args.cover_bg_color,
        text_color=args.cover_text_color,
    )
    theme_keyword = _resolve_theme_keyword(args.theme_keyword)
    logger.info("theme_keyword: %s", theme_keyword)
    logger.info("cover_enabled: %s", args.cover_enabled)
    sizes = _mode_sizes(args)

    image_manifest: list[dict[str, Any]] = []
    segment_manifest: list[dict[str, Any]] = []
    outputs: list[Path] = []

    for mode in modes:
        size = sizes[mode]
        images_dir = _mode_dir(paths["images_dir"], mode, is_multi_mode)
        clips_dir = _mode_dir(paths["segments_dir"], mode, is_multi_mode)

        cover_path = render_cover_image(
            mode=mode,
            size=size,
            settings=cover_settings,
            theme_keyword=theme_keyword,
            font_path=settings.font_path,
            out_dir=images_dir,
            logger=logger,
        )
        image_manifest.append(
            {
                "type": "cover",
                "mode": mode,
                "index": 0,
                "keyword": theme_keyword,
                "image_path": str(cover_path),
            }
        )

        image_paths = render_images_for_mode(
            sentences=sentences,
            mode=mode,
            size=size,
            settings=settings,
            overlay_resolver=overlay_resolver,
            out_dir=images_dir,
            logger=logger,
            max_workers=args.image_workers,
        )
        for idx, image_path in enumerate(image_paths, start=1):
            image_manifest.append(
                {
                    "mode": mode,
                    "index": idx,
                    "text": sentences[idx - 1],
                    "image_path": str(image_path),
                }
            )

        segment_paths = create_clips_for_mode(
            audio_items=audio_items,
            images_dir=images_dir,
            clips_dir=clips_dir,
            fps=args.fps,
            tts_start_offset=args.tts_start_offset,
            logger=logger,
            max_workers=args.clip_workers,
        )
        for idx, segment_path in enumerate(segment_paths, start=1):
            segment_manifest.append(
                {
                    "mode": mode,
                    "index": idx,
                    "text": sentences[idx - 1],
                    "video_path": str(segment_path),
                    "duration": audio_items[idx - 1].duration
                    + (args.tts_start_offset if idx == 1 else 0.0),
                }
            )

        concat_name = "concat_list.txt" if not is_multi_mode else f"concat_{mode}.txt"
        concat_file = write_concat_file(
            mode=mode,
            clips_dir=clips_dir,
            concat_dir=paths["final_dir"],
            total_count=len(audio_items),
            file_name=concat_name,
        )

        raw_name = "final_raw.mp4" if not is_multi_mode else f"final_raw_{mode}.mp4"
        raw_output = paths["final_dir"] / raw_name
        merged = concat_mode_video(
            mode=mode,
            concat_file=concat_file,
            output_path=raw_output,
            fps=args.fps,
            logger=logger,
        )
        logger.info("%s raw video generated: %s", mode, merged)

        source_video = merged
        if args.cover_enabled:
            cover_name = "final_cover_raw.mp4" if not is_multi_mode else f"final_cover_raw_{mode}.mp4"
            cover_output = paths["final_dir"] / cover_name
            source_video = overlay_cover_on_first_frame(
                video_path=Path(merged),
                cover_path=cover_path,
                output_path=cover_output,
                fps=args.fps,
                logger=logger,
            )
            logger.info("%s cover-first-frame video generated: %s", mode, source_video)

        if args.bgm_enabled:
            final_name = "final.mp4" if not is_multi_mode else f"final_{mode}.mp4"
            mixed = mix_bgm(
                video_path=source_video,
                bgm_path=args.bgm_file,
                out_path=paths["final_dir"] / final_name,
                volume=args.bgm_volume,
                fade_in=args.bgm_fade_in,
                fade_out=args.bgm_fade_out,
                audio_bitrate=args.bgm_audio_bitrate,
                logger=logger,
            )
            outputs.append(mixed)
        else:
            final_name = "final.mp4" if not is_multi_mode else f"final_{mode}.mp4"
            final_target = paths["final_dir"] / final_name
            if final_target.exists():
                final_target.unlink()
            Path(source_video).replace(final_target)
            outputs.append(final_target)

    _write_json(paths["images_dir"] / "image_manifest.json", image_manifest)
    _write_json(paths["segments_dir"] / "segments_manifest.json", segment_manifest)

    return outputs


def main() -> None:
    parser = _build_parser()
    raw_args = parser.parse_args()
    resolved = _merge_args(raw_args)
    outputs = run(resolved)
    for item in outputs:
        print(item)


if __name__ == "__main__":
    main()
