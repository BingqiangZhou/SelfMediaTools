from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ffmpeg_utils import run_cmd
from models import AudioItem, OutputMode, numbered_name

MAX_CLIP_RETRIES = 3


def _default_clip_workers() -> int:
    cpu = os.cpu_count() or 4
    return max(1, min(4, cpu))


def _create_single_clip(
    item: AudioItem,
    images_dir: Path,
    clips_dir: Path,
    fps: int,
    tts_start_offset: float,
    logger: logging.Logger | None,
) -> tuple[int, Path]:
    image_path = images_dir / numbered_name(item.index, "png")
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found for clip {item.index}: {image_path}")

    clip_path = clips_dir / numbered_name(item.index, "mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(fps),
        "-i",
        str(image_path),
        "-i",
        str(item.audio_path),
    ]
    clip_delay = tts_start_offset if item.index == 1 else 0.0
    if clip_delay > 0:
        delay_ms = int(round(clip_delay * 1000))
        cmd.extend(["-filter:a", f"adelay={delay_ms}:all=1"])
    cmd.extend([
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(clip_path),
    ])

    last_exc: Exception | None = None
    for attempt in range(1, MAX_CLIP_RETRIES + 1):
        try:
            run_cmd(cmd, logger=logger, check=True)
            if logger:
                logger.info("clip generated: %s", clip_path)
            return item.index, clip_path.resolve()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if logger:
                logger.warning(
                    "clip generation failed #%03d attempt=%d/%d: %s",
                    item.index,
                    attempt,
                    MAX_CLIP_RETRIES,
                    exc,
                )
            if clip_path.exists():
                clip_path.unlink()
            if attempt < MAX_CLIP_RETRIES:
                time.sleep(float(attempt))

    raise RuntimeError(
        f"Failed to generate clip after {MAX_CLIP_RETRIES} attempts: {clip_path}"
    ) from last_exc


def create_clips_for_mode(
    audio_items: list[AudioItem],
    images_dir: Path,
    clips_dir: Path,
    fps: int,
    tts_start_offset: float = 1.0,
    logger: logging.Logger | None = None,
    max_workers: int | None = None,
) -> list[Path]:
    clips_dir.mkdir(parents=True, exist_ok=True)
    workers = max_workers or _default_clip_workers()
    if workers <= 0:
        raise ValueError("max_workers for clip generation must be > 0")

    if len(audio_items) <= 1 or workers == 1:
        ordered: dict[int, Path] = {}
        for item in audio_items:
            index, path = _create_single_clip(
                item=item,
                images_dir=images_dir,
                clips_dir=clips_dir,
                fps=fps,
                tts_start_offset=tts_start_offset,
                logger=logger,
            )
            ordered[index] = path
        return [ordered[index] for index in range(1, len(audio_items) + 1)]

    futures = {}
    ordered: dict[int, Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for item in audio_items:
            future = executor.submit(
                _create_single_clip,
                item,
                images_dir,
                clips_dir,
                fps,
                tts_start_offset,
                logger,
            )
            futures[future] = item.index

        for future in as_completed(futures):
            index, path = future.result()
            ordered[index] = path

    return [ordered[index] for index in range(1, len(audio_items) + 1)]


def _concat_line(path: Path) -> str:
    escaped = path.resolve().as_posix().replace("'", "'\\''")
    return f"file '{escaped}'"


def write_concat_file(
    mode: OutputMode,
    clips_dir: Path,
    concat_dir: Path,
    total_count: int,
    file_name: str | None = None,
) -> Path:
    concat_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index in range(1, total_count + 1):
        clip_path = clips_dir / numbered_name(index, "mp4")
        if not clip_path.exists():
            raise FileNotFoundError(f"Missing clip for concat: {clip_path}")
        lines.append(_concat_line(clip_path))
    concat_path = concat_dir / (file_name or f"{mode}.txt")
    concat_path.write_text("\n".join(lines), encoding="utf-8")
    return concat_path


def concat_mode_video(
    mode: OutputMode,
    concat_file: Path,
    output_path: Path,
    fps: int,
    logger: logging.Logger | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(output_path),
    ]
    run_cmd(cmd, logger=logger, check=True)
    if logger:
        logger.info("%s output generated: %s", mode, output_path)
    return output_path.resolve()
