from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path


def format_cmd(cmd: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def ensure_ffmpeg_tools() -> None:
    missing = [binary for binary in ("ffmpeg", "ffprobe") if shutil.which(binary) is None]
    if not missing:
        return
    details = ", ".join(missing)
    raise RuntimeError(
        "Missing required binaries in PATH: "
        f"{details}. Install ffmpeg/ffprobe first.\n"
        "Windows: winget install Gyan.FFmpeg\n"
        "macOS: brew install ffmpeg\n"
        "Ubuntu/Debian: sudo apt-get install ffmpeg"
    )


def run_cmd(
    cmd: list[str],
    logger: logging.Logger | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    if logger:
        logger.info("run: %s", format_cmd(cmd))
    completed = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            "Command failed\n"
            f"cmd: {format_cmd(cmd)}\n"
            f"exit_code: {completed.returncode}\n"
            f"stderr: {(completed.stderr or '').strip()}"
        )
    return completed


def probe_duration(path: str | Path, logger: logging.Logger | None = None) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    completed = run_cmd(cmd, logger=logger, check=True)
    raw = (completed.stdout or "").strip()
    try:
        duration = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"Unable to parse ffprobe duration from output: {raw!r}") from exc
    if duration <= 0:
        raise RuntimeError(f"Duration must be > 0, got: {duration}")
    return duration


def probe_duration_seconds(path: str | Path, logger: logging.Logger | None = None) -> float:
    return probe_duration(path, logger=logger)


def probe_has_audio_stream(path: str | Path, logger: logging.Logger | None = None) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ]
    completed = run_cmd(cmd, logger=logger, check=True)
    return bool((completed.stdout or "").strip())
