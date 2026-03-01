"""
视频生成配置辅助脚本
用于展示和管理视频生成器的配置选项
"""

import sys
import io

# 设置UTF-8编码输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from typing import Any


# 默认配置
DEFAULTS = {
    # 默认配置文件路径
    "config_file": "configs/1.yaml",

    # 输入设置
    "text": None,
    "text_file": "assets/sample_input.txt",

    # TTS语音设置
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+0%",
    "volume": "+0%",
    "tts_start_offset": 1.0,

    # 输出设置
    "output_modes": "portrait,landscape",
    "portrait_size": "1080x1920",
    "landscape_size": "1920x1080",
    "fps": 30,

    # 并发设置
    "tts_workers": 4,
    "image_workers": 4,
    "clip_workers": 2,
    "work_dir": "output",

    # 文字卡片样式
    "font_path": "C:/Windows/Fonts/msyh.ttc",
    "font_size": 72,
    "min_font_size": 28,
    "line_spacing": 1.25,
    "text_margin_x": 80,
    "text_margin_y": 60,
    "bg_color": "#000000",
    "text_color": "#FFFFFF",

    # 叠加图片设置
    "overlay_image": None,
    "overlay_dir": None,
    "overlay_height_ratio": 0.35,
    "overlay_box_width_ratio": 0.68,
    "overlay_fit": "cover",
    "overlay_top_margin": 48,
    "overlay_text_gap": 12,

    # BGM设置
    "bgm_enabled": False,
    "bgm_file": "./assets/bgm.MP3",
    "bgm_volume": 0.18,
    "bgm_fade_in": 1.5,
    "bgm_fade_out": 1.5,
    "bgm_audio_bitrate": "192k",
}


# 配置分组
CONFIG_GROUPS = {
    "输入设置": {
        "description": "文本输入源配置",
        "keys": ["text", "text_file"],
        "options": [
            {
                "key": "text",
                "label": "直接输入文本",
                "type": "string",
                "default": None,
                "hint": "直接提供要转换为视频的文本内容"
            },
            {
                "key": "text_file",
                "label": "文本文件路径",
                "type": "path",
                "default": "assets/sample_input.txt",
                "hint": "包含要转换文本的文件路径"
            }
        ]
    },
    "TTS语音设置": {
        "description": "文本转语音配置",
        "keys": ["voice", "rate", "volume", "tts_start_offset"],
        "options": [
            {
                "key": "voice",
                "label": "语音类型",
                "type": "choice",
                "choices": [
                    "zh-CN-XiaoxiaoNeural",
                    "zh-CN-YunxiNeural",
                    "zh-CN-YunyangNeural",
                    "zh-CN-XiaoyiNeural"
                ],
                "default": "zh-CN-XiaoxiaoNeural",
                "hint": "女声-温柔"
            },
            {
                "key": "rate",
                "label": "语速",
                "type": "range",
                "min": -50,
                "max": 100,
                "unit": "%",
                "default": "+0%",
                "hint": "范围: -50% 到 +100%"
            },
            {
                "key": "volume",
                "label": "音量",
                "type": "range",
                "min": -50,
                "max": 50,
                "unit": "%",
                "default": "+0%",
                "hint": "范围: -50% 到 +50%"
            },
            {
                "key": "tts_start_offset",
                "label": "首段延迟",
                "type": "float",
                "min": 0,
                "max": 5,
                "step": 0.5,
                "unit": "秒",
                "default": 1.0,
                "hint": "第一个视频片段的开始延迟"
            }
        ]
    },
    "输出设置": {
        "description": "视频输出格式配置",
        "keys": ["output_modes", "portrait_size", "landscape_size", "fps"],
        "options": [
            {
                "key": "output_modes",
                "label": "输出模式",
                "type": "multichoice",
                "choices": ["portrait", "landscape"],
                "default": "portrait,landscape",
                "hint": "portrait=竖屏, landscape=横屏"
            },
            {
                "key": "portrait_size",
                "label": "竖屏尺寸",
                "type": "choice",
                "choices": ["1080x1920", "720x1280", "2160x3840"],
                "default": "1080x1920",
                "hint": "抖音/快手等平台"
            },
            {
                "key": "landscape_size",
                "label": "横屏尺寸",
                "type": "choice",
                "choices": ["1920x1080", "1280x720", "3840x2160"],
                "default": "1920x1080",
                "hint": "B站/YouTube等平台"
            },
            {
                "key": "fps",
                "label": "帧率",
                "type": "choice",
                "choices": [24, 25, 30, 60],
                "default": 30,
                "hint": "视频每秒帧数"
            }
        ]
    },
    "并发设置": {
        "description": "并行处理线程数配置",
        "keys": ["tts_workers", "image_workers", "clip_workers"],
        "options": [
            {
                "key": "tts_workers",
                "label": "TTS并发数",
                "type": "range",
                "min": 1,
                "max": 10,
                "default": 4,
                "hint": "语音合成并发线程数"
            },
            {
                "key": "image_workers",
                "label": "图片渲染并发数",
                "type": "range",
                "min": 1,
                "max": 10,
                "default": 4,
                "hint": "图片渲染并发线程数"
            },
            {
                "key": "clip_workers",
                "label": "视频片段并发数",
                "type": "range",
                "min": 1,
                "max": 5,
                "default": 2,
                "hint": "视频片段生成并发线程数"
            }
        ]
    },
    "文字卡片样式": {
        "description": "文本卡片外观配置",
        "keys": ["font_path", "font_size", "min_font_size", "line_spacing",
                 "text_margin_x", "text_margin_y", "bg_color", "text_color"],
        "options": [
            {
                "key": "font_path",
                "label": "字体文件",
                "type": "path",
                "default": "C:/Windows/Fonts/msyh.ttc",
                "hint": "中文字体文件路径"
            },
            {
                "key": "font_size",
                "label": "字体大小",
                "type": "range",
                "min": 36,
                "max": 120,
                "default": 72,
                "hint": "正常字体大小"
            },
            {
                "key": "min_font_size",
                "label": "最小字体",
                "type": "range",
                "min": 16,
                "max": 48,
                "default": 28,
                "hint": "自动缩小时的最小值"
            },
            {
                "key": "line_spacing",
                "label": "行间距",
                "type": "float",
                "min": 1.0,
                "max": 2.0,
                "step": 0.05,
                "default": 1.25,
                "hint": "行与行之间的间距倍数"
            },
            {
                "key": "text_margin_x",
                "label": "水平边距",
                "type": "range",
                "min": 0,
                "max": 200,
                "default": 80,
                "hint": "文字左右边距"
            },
            {
                "key": "text_margin_y",
                "label": "垂直边距",
                "type": "range",
                "min": 0,
                "max": 200,
                "default": 60,
                "hint": "文字上下边距"
            },
            {
                "key": "bg_color",
                "label": "背景颜色",
                "type": "color",
                "default": "#000000",
                "hint": "卡片背景颜色"
            },
            {
                "key": "text_color",
                "label": "文字颜色",
                "type": "color",
                "default": "#FFFFFF",
                "hint": "文本文字颜色"
            }
        ]
    },
    "叠加图片设置": {
        "description": "顶部叠加图片配置",
        "keys": ["overlay_image", "overlay_dir", "overlay_height_ratio",
                 "overlay_box_width_ratio", "overlay_fit", "overlay_top_margin", "overlay_text_gap"],
        "options": [
            {
                "key": "overlay_image",
                "label": "固定图片路径",
                "type": "path",
                "default": None,
                "hint": "所有句子使用同一张图片"
            },
            {
                "key": "overlay_dir",
                "label": "图片目录",
                "type": "path",
                "default": None,
                "hint": "每个句子使用目录中对应图片"
            },
            {
                "key": "overlay_height_ratio",
                "label": "图片高度占比",
                "type": "float",
                "min": 0.1,
                "max": 0.8,
                "step": 0.05,
                "default": 0.35,
                "hint": "图片占画面高度的比例"
            },
            {
                "key": "overlay_box_width_ratio",
                "label": "图片区域宽度",
                "type": "float",
                "min": 0.3,
                "max": 1.0,
                "step": 0.05,
                "default": 0.68,
                "hint": "图片区域占画面宽度的比例"
            },
            {
                "key": "overlay_fit",
                "label": "适配方式",
                "type": "choice",
                "choices": ["cover", "contain"],
                "default": "cover",
                "hint": "cover=填充, contain=包含"
            },
            {
                "key": "overlay_top_margin",
                "label": "顶部边距",
                "type": "range",
                "min": 0,
                "max": 200,
                "default": 48,
                "hint": "图片距离顶部的距离"
            },
            {
                "key": "overlay_text_gap",
                "label": "图文间距",
                "type": "range",
                "min": 0,
                "max": 100,
                "default": 12,
                "hint": "图片与文字之间的间隙"
            }
        ]
    },
    "背景音乐(BGM)设置": {
        "description": "背景音乐配置",
        "keys": ["bgm_enabled", "bgm_file", "bgm_volume", "bgm_fade_in", "bgm_fade_out", "bgm_audio_bitrate"],
        "options": [
            {
                "key": "bgm_enabled",
                "label": "启用BGM",
                "type": "bool",
                "default": False,
                "hint": "是否添加背景音乐"
            },
            {
                "key": "bgm_file",
                "label": "BGM文件路径",
                "type": "path",
                "default": "./assets/bgm.MP3",
                "hint": "背景音乐文件路径"
            },
            {
                "key": "bgm_volume",
                "label": "BGM音量",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "default": 0.18,
                "hint": "背景音乐音量(0-1)"
            },
            {
                "key": "bgm_fade_in",
                "label": "淡入时长",
                "type": "float",
                "min": 0,
                "max": 5,
                "step": 0.5,
                "default": 1.5,
                "hint": "背景音乐淡入秒数"
            },
            {
                "key": "bgm_fade_out",
                "label": "淡出时长",
                "type": "float",
                "min": 0,
                "max": 5,
                "step": 0.5,
                "default": 1.5,
                "hint": "背景音乐淡出秒数"
            },
            {
                "key": "bgm_audio_bitrate",
                "label": "音频比特率",
                "type": "choice",
                "choices": ["128k", "192k", "256k", "320k"],
                "default": "192k",
                "hint": "输出音频比特率"
            }
        ]
    }
}


def get_config_summary(config: dict[str, Any] | None = None) -> str:
    """生成配置摘要文本"""
    cfg = config or DEFAULTS

    summary_lines = ["# 视频生成配置摘要\n"]

    for group_name, group_data in CONFIG_GROUPS.items():
        summary_lines.append(f"## {group_name}")
        summary_lines.append(f"*{group_data['description']}*\n")

        for opt in group_data["options"]:
            key = opt["key"]
            value = cfg.get(key, opt.get("default"))
            label = opt["label"]
            hint = opt.get("hint", "")

            # 格式化值显示
            if value is None:
                value_str = "(未设置)"
            elif isinstance(value, bool):
                value_str = "是" if value else "否"
            else:
                value_str = str(value)

            summary_lines.append(f"**{label}**: `{value_str}`")
            if hint:
                summary_lines.append(f"  - {hint}")
        summary_lines.append("")

    return "\n".join(summary_lines)


def build_command_args(config: dict[str, Any]) -> list[str]:
    """将配置转换为命令行参数"""
    args = ["uv", "run", "main.py"]

    # 如果使用配置文件（默认行为）
    config_file = config.get("config_file", DEFAULTS.get("config_file", "configs/1.yaml"))
    if config_file:
        args.extend(["--config", config_file])
        return args

    # CLI参数映射（当不使用配置文件时）
    param_map = {
        "text": "--text",
        "text_file": "--text-file",
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
        if value is not None and value != DEFAULTS.get(key):
            # 布尔值特殊处理
            if isinstance(value, bool):
                args.append(f"{cli_param}={str(value).lower()}")
            else:
                args.append(f"{cli_param}")
                args.append(str(value))

    return args


if __name__ == "__main__":
    # 打印配置摘要
    print(get_config_summary())

    # 打印示例命令
    print("\n# 示例命令")
    print(" ".join(build_command_args(DEFAULTS)))
