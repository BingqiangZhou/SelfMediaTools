from __future__ import annotations

import logging
from pathlib import Path

from ffmpeg_utils import probe_duration_seconds, probe_has_audio_stream, run_cmd


def _build_mix_cmd(
    video_path: Path,
    bgm_path: Path,
    out_path: Path,
    volume: float,
    fade_in: float,
    fade_out: float,
    audio_bitrate: str,
    reencode_video: bool,
    logger: logging.Logger | None,
) -> list[str]:
    video_duration = probe_duration_seconds(video_path, logger=logger)
    fade_out_start = max(video_duration - fade_out, 0.0)
    bgm_filters = [f"volume={volume}"]
    if fade_in > 0:
        bgm_filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        bgm_filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")
    filter_complex = (
        f"[1:a]{','.join(bgm_filters)}[bgm];"
        "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-stream_loop",
        "-1",
        "-i",
        str(bgm_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-shortest",
    ]
    if reencode_video:
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    else:
        cmd.extend(["-c:v", "copy"])
    cmd.append(str(out_path))
    return cmd


def mix_bgm(
    video_path: str | Path,
    bgm_path: str | Path,
    out_path: str | Path,
    volume: float,
    fade_in: float,
    fade_out: float,
    audio_bitrate: str,
    logger: logging.Logger | None = None,
) -> Path:
    video = Path(video_path).resolve()
    bgm = Path(bgm_path).resolve()
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video}")
    if not bgm.exists():
        raise FileNotFoundError(f"BGM not found: {bgm}")
    if not probe_has_audio_stream(video, logger=logger):
        raise RuntimeError(f"Input video has no audio stream: {video}")

    cmd_copy = _build_mix_cmd(
        video_path=video,
        bgm_path=bgm,
        out_path=out,
        volume=volume,
        fade_in=fade_in,
        fade_out=fade_out,
        audio_bitrate=audio_bitrate,
        reencode_video=False,
        logger=logger,
    )
    try:
        run_cmd(cmd_copy, logger=logger, check=True)
        return out
    except RuntimeError as exc:
        if logger:
            logger.warning("BGM mix with -c:v copy failed, fallback to re-encode: %s", exc)

    cmd_reencode = _build_mix_cmd(
        video_path=video,
        bgm_path=bgm,
        out_path=out,
        volume=volume,
        fade_in=fade_in,
        fade_out=fade_out,
        audio_bitrate=audio_bitrate,
        reencode_video=True,
        logger=logger,
    )
    run_cmd(cmd_reencode, logger=logger, check=True)
    return out
