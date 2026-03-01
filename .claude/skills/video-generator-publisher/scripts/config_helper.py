"""Helper utilities for video-generator-publisher skill config and CLI mapping."""

from __future__ import annotations

from typing import Any


DEFAULTS: dict[str, Any] = {
    "config_file": "configs/1.yaml",
    "text": None,
    "text_file": "assets/sample_input.txt",
    "theme_keyword": None,
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+0%",
    "volume": "+0%",
    "tts_start_offset": 1.0,
    "output_modes": "portrait,landscape",
    "portrait_size": "1080x1920",
    "landscape_size": "1920x1080",
    "fps": 30,
    "tts_workers": 4,
    "image_workers": 4,
    "clip_workers": 2,
    "work_dir": "output",
    "font_path": "C:/Windows/Fonts/msyh.ttc",
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
    "bgm_enabled": False,
    "bgm_file": "./assets/bgm.MP3",
    "bgm_volume": 0.18,
    "bgm_fade_in": 1.5,
    "bgm_fade_out": 1.5,
    "bgm_audio_bitrate": "192k",
}


CONFIG_GROUPS: dict[str, dict[str, Any]] = {
    "input": {
        "description": "Input source and topic keyword",
        "keys": ["text", "text_file", "theme_keyword"],
        "options": [
            {
                "key": "text",
                "label": "Text",
                "type": "string",
                "default": None,
                "hint": "Direct text content",
            },
            {
                "key": "text_file",
                "label": "Text File",
                "type": "path",
                "default": "assets/sample_input.txt",
                "hint": "Path of input text file",
            },
            {
                "key": "theme_keyword",
                "label": "Theme Keyword",
                "type": "string",
                "default": None,
                "hint": "AI summary keyword passed to --theme-keyword",
            },
        ],
    },
    "tts": {
        "description": "TTS settings",
        "keys": ["voice", "rate", "volume", "tts_start_offset"],
        "options": [],
    },
    "output": {
        "description": "Video output settings",
        "keys": ["output_modes", "portrait_size", "landscape_size", "fps"],
        "options": [],
    },
    "render": {
        "description": "Render style settings",
        "keys": [
            "font_path",
            "font_size",
            "min_font_size",
            "line_spacing",
            "text_margin_x",
            "text_margin_y",
            "bg_color",
            "text_color",
            "overlay_image",
            "overlay_dir",
            "overlay_height_ratio",
            "overlay_box_width_ratio",
            "overlay_fit",
            "overlay_top_margin",
            "overlay_text_gap",
        ],
        "options": [],
    },
    "bgm": {
        "description": "Background music settings",
        "keys": [
            "bgm_enabled",
            "bgm_file",
            "bgm_volume",
            "bgm_fade_in",
            "bgm_fade_out",
            "bgm_audio_bitrate",
        ],
        "options": [],
    },
}


def get_config_summary(config: dict[str, Any] | None = None) -> str:
    cfg = config or DEFAULTS
    lines = ["# Video Generator Config Summary", ""]
    for group_name, group_data in CONFIG_GROUPS.items():
        lines.append(f"## {group_name}")
        lines.append(str(group_data.get("description", "")))
        for key in group_data.get("keys", []):
            lines.append(f"- {key}: {cfg.get(key)!r}")
        lines.append("")
    return "\n".join(lines)


def build_command_args(config: dict[str, Any]) -> list[str]:
    args = ["uv", "run", "main.py"]

    config_file = config.get("config_file", DEFAULTS.get("config_file", "configs/1.yaml"))
    if config_file:
        args.extend(["--config", str(config_file)])

    param_map = {
        "text": "--text",
        "text_file": "--text-file",
        "theme_keyword": "--theme-keyword",
        "voice": "--voice",
        "rate": "--rate",
        "volume": "--volume",
        "tts_start_offset": "--tts-start-offset",
        "output_modes": "--output-modes",
        "portrait_size": "--portrait-size",
        "landscape_size": "--landscape-size",
        "fps": "--fps",
        "font_path": "--font-path",
        "font_size": "--font-size",
        "min_font_size": "--min-font-size",
        "line_spacing": "--line-spacing",
        "text_margin_x": "--text-margin-x",
        "text_margin_y": "--text-margin-y",
        "bg_color": "--bg-color",
        "text_color": "--text-color",
        "overlay_image": "--overlay-image",
        "overlay_dir": "--overlay-dir",
        "overlay_height_ratio": "--overlay-height-ratio",
        "overlay_box_width_ratio": "--overlay-box-width-ratio",
        "overlay_fit": "--overlay-fit",
        "overlay_top_margin": "--overlay-top-margin",
        "overlay_text_gap": "--overlay-text-gap",
        "tts_workers": "--tts-workers",
        "image_workers": "--image-workers",
        "clip_workers": "--clip-workers",
        "work_dir": "--work-dir",
        "bgm_enabled": "--bgm-enabled",
        "bgm_file": "--bgm-file",
        "bgm_volume": "--bgm-volume",
        "bgm_fade_in": "--bgm-fade-in",
        "bgm_fade_out": "--bgm-fade-out",
        "bgm_audio_bitrate": "--bgm-audio-bitrate",
    }

    for key, cli_param in param_map.items():
        value = config.get(key)
        if value is None or value == DEFAULTS.get(key):
            continue
        if isinstance(value, bool):
            args.extend([cli_param, str(value).lower()])
        else:
            args.extend([cli_param, str(value)])

    return args


if __name__ == "__main__":
    print(get_config_summary())
    print("\n# Example Command")
    print(" ".join(build_command_args(DEFAULTS)))
