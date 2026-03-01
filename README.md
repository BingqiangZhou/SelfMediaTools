# Self Media Tools

Text -> sentence TTS -> sentence card images (top overlay + bottom text) -> portrait/landscape videos.

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
- `cover_prefix_text`: first line text (default empty, no prefix line)
- `cover_bg_color`: cover background color
- `cover_text_color`: cover text color
- TTS start: `tts_start_offset` controls when the first TTS segment starts (seconds, default `1.0`)
- Overlay layout tuning:
- `overlay_height_ratio`: overlay box height ratio of canvas
- `overlay_box_width_ratio`: max overlay side ratio by width (overlay uses a square box in both modes)
- `overlay_top_margin`: top margin for overlay box (px)
- `overlay_text_gap`: vertical gap between overlay and text block (px)
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

## Notes

- `overlay_dir` matches by index: `0001.png/jpg/jpeg/webp/bmp` (also compatible with `001.*`).
- Missing per-sentence overlay falls back to `overlay_image`.
- If both are unavailable, cards are rendered with text-only layout.
- BGM shorter than video is looped automatically to cover full duration.
