from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from video import overlay_cover_on_first_frame


def _run(cmd: list[str]) -> None:
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{completed.stderr}")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_overlay_cover_only_first_frame(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    cover = tmp_path / "cover.png"
    output = tmp_path / "out.mp4"
    frame0 = tmp_path / "frame0.png"
    frame1 = tmp_path / "frame1.png"

    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=1:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=1",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ]
    )

    Image.new("RGB", (320, 240), (255, 0, 0)).save(cover, format="PNG")
    out_path = overlay_cover_on_first_frame(
        video_path=source,
        cover_path=cover,
        output_path=output,
        fps=30,
    )
    assert out_path.exists()

    _run(["ffmpeg", "-y", "-i", str(out_path), "-vf", "select=eq(n\\,0)", "-vframes", "1", str(frame0)])
    _run(["ffmpeg", "-y", "-i", str(out_path), "-vf", "select=eq(n\\,1)", "-vframes", "1", str(frame1)])

    with Image.open(frame0) as first, Image.open(frame1) as second:
        f_r, f_g, f_b = first.getpixel((160, 120))
        s_r, s_g, s_b = second.getpixel((160, 120))

    assert f_r > 180 and f_g < 80 and f_b < 80
    assert s_b > 120 and s_r < 120
