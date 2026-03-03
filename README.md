# Self Media Tools

Text -> sentence TTS -> sentence card images (top overlay + bottom text) -> portrait/landscape videos.

## Claude Skill

**video-generator-publisher** v0.0.2 | Updated: 2026-03-02 | Author: Bingqiang Zhou

用于生成自媒体短视频并支持发布到抖音的 Claude Code 技能。

**功能**:
- 支持竖屏(1080x1920)和横屏(1920x1080)两种输出格式
- 自动生成"共鸣向上、温暖励志"风格的文案内容
- 自动发布到抖音创作者平台
- 支持选择视频首帧作为封面
- 支持标题和文案内容填写
- 不允许下载设置

**技能文件**: `.claude/skills/video-generator-publisher/`

## Requirements

- Python 3.10+
- `uv`
- `ffmpeg` / `ffprobe` in `PATH`

## Install

```bash
uv sync
```

## Config-first Run

1. Edit `configs/config.yaml`.
2. Run the full pipeline directly from config:

```bash
uv run python main.py --config configs/config.yaml
```

Equivalent module mode:

```bash
uv run python -m main --config configs/config.yaml
```

## BGM Config

Use nested `bgm` in `configs/config.yaml`:

```yaml
bgm:
  enabled: false
  file: null
  volume: 0.18
  fade_in: 1.5
  fade_out: 1.5
  audio_bitrate: "192k"
```

When `bgm.enabled=true`:

- keep raw merged video under `05_final/final_raw*.mp4`
- generate final BGM video under `05_final/final*.mp4`

## CLI Override

You can override any config key by CLI args. Example:

```bash
uv run python main.py --config configs/config.yaml --bgm-enabled true --bgm-file assets/bgm.MP3 --bgm-volume 0.2
```

Cover first-frame example:

```bash
uv run python main.py --config configs/config.yaml --theme-keyword "天命之人" --cover-enabled true
```

## Required Config Keys

- Input: `text` or `text_file` (at least one)
- Render: `font_path` (required)
- BGM: `bgm.file` required only when `bgm.enabled=true`
- Cover keyword: `theme_keyword` is optional; empty value falls back to `天命之人`
- Cover switch: `cover_enabled=true` overlays generated cover on frame `#0` only
- Cover style:
- `cover_bg_color`: cover background color
- `cover_text_color`: cover text color
- TTS start: `tts_start_offset` controls when the first TTS segment starts (seconds, default `1.0`)
- Overlay layout tuning:
- `overlay_height_ratio`: overlay box height ratio of canvas
- `overlay_box_width_ratio`: max overlay side ratio by width (overlay uses a square box in both modes)
- `overlay_top_margin`: top margin for overlay box (px)
- `overlay_text_gap`: vertical gap between overlay and text block (px)
- Subtitle render mode:
- `subtitle_render_mode`: `classic` (existing effects) or `flip_big` (`SRT+ASS` burn-in pipeline)
- `flip_big_style`: `progressive` (word-by-word) or `sentence` (whole sentence)
- `flip_big_max_lines`: max retained lines for `progressive` mode before rolling window trim
- `flip_big_anchor_y_ratio`: anchor Y ratio for `progressive` mode (`0~1`, default `0.56`)
- `flip_big_sentence_anchor_y_ratio`: anchor Y ratio for `sentence` mode (`0~1`, default `0.50`)
- Parallel workers:
- `tts_workers`: concurrent TTS tasks
- `image_workers`: concurrent image render tasks
- `clip_workers`: concurrent ffmpeg clip tasks

## Output Layout

Each run is written under `work_dir/run_YYYYMMDD_HHMMSS/`:

```text
output/
  run_20260301_094443/
    01_sentences/
      sentences.json
    02_images/
      0001.png ...
      image_manifest.json
    03_audio/
      0001.mp3 ...
      audio_manifest.json
    04_segments/
      0001.mp4 ...
      0001.srt ...
      0001.ass ...
      segments_manifest.json
    05_final/
      concat_list.txt
      final_raw.mp4
      final_cover_raw.mp4
      final.mp4
    logs/
      pipeline.log
```

For multi-mode output, `02_images/` and `04_segments/` will contain mode subfolders, and `05_final/` uses mode suffixes.

When `subtitle_render_mode=flip_big`, `04_segments[/mode]/` keeps one `.srt` (timeline/debug) and one `.ass` (animated burn-in source) per sentence clip.

## Notes

- `overlay_dir` matches by index: `0001.png/jpg/jpeg/webp/bmp` (also compatible with `001.*`).
- Missing per-sentence overlay falls back to `overlay_image`.
- If both are unavailable, cards are rendered with text-only layout.
- BGM shorter than video is looped automatically to cover full duration.
