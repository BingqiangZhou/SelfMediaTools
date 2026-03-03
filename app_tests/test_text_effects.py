import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from models import AudioItem, CanvasSize, RenderSettings
from video import _create_single_clip


def _run(cmd: list[str]) -> None:
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{completed.stderr}")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_text_effects(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    
    # Create silent audio for the test clip
    audio_path = tmp_path / "silent.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2", str(audio_path)])
    
    # We'll test slide_left, fadein, and rotate
    test_cases = [
        (1, "slide_left"),
        (2, "fadein"),
        (3, "rotate"),
    ]
    
    for index, effect in test_cases:
        item = AudioItem(index=index, text=f"Test {effect}", audio_path=audio_path, duration=2.0)
        size = CanvasSize(width=640, height=360)
        
        # Determine a fallback font that works on Windows
        font_path = Path("C:/Windows/Fonts/msyh.ttc")
        if not font_path.exists():
            font_path = Path("C:/Windows/Fonts/simhei.ttf")
            
        settings = RenderSettings(
            font_path=font_path,
            font_size=40,
            min_font_size=20,
            line_spacing=1.25,
            text_margin_x=40,
            text_margin_y=40,
            bg_color="#000000",
            text_color="#FFFFFF",
            text_colors=(),
            text_effects=(effect,),
            effect_duration=1.0,  # 1 second effect
            use_text_effects=True,
            random_color=False,
            random_effect=False,
        )
        
        idx, out_path = _create_single_clip(
            item=item,
            sentences=[item.text],
            size=size,
            settings=settings,
            clips_dir=clips_dir,
            fps=30,
            tts_start_offset=0.0,
            logger=None,
        )
        assert out_path.exists()
        
        # Extract frame at t=0 and t=1.0 (end of effect)
        frame0 = tmp_path / f"frame0_{effect}.png"
        frame1 = tmp_path / f"frame1_{effect}.png"
        
        _run(["ffmpeg", "-y", "-ss", "00:00:00", "-i", str(out_path), "-frames:v", "1", str(frame0)])
        _run(["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(out_path), "-frames:v", "1", str(frame1)])
        
        with Image.open(frame0) as f0, Image.open(frame1) as f1:
            # For slide_left, t=0 should be off-screen or animating in, t=1.0 should be centered
            if effect == "slide_left":
                # Check center pixel at t=1.0 has text (white), while t=0 might be black
                pass # We mainly check that the file runs and generates without error 
            
            # Simple check that the frames are different, meaning animation happened
            # Calculate difference
            from PIL import ImageChops
            diff = ImageChops.difference(f0, f1)
            assert diff.getbbox() is not None, f"Effect {effect} showed no visual difference between t=0 and t=1.0!"
