import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageChops

def _run(cmd):
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{completed.stderr}")

def main():
    import sys
    sys.path.insert(0, str(Path("src").resolve()))
    from models import AudioItem, CanvasSize, RenderSettings
    from video import _create_single_clip

    out_dir = Path("output_test_effects")
    out_dir.mkdir(exist_ok=True)
    
    audio_path = out_dir / "silent.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2", str(audio_path)])
    
    test_cases = [
        (1, "slide_left"),
        (2, "fadein"),
        (3, "rotate"),
    ]
    
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists():
        font_path = Path("C:/Windows/Fonts/simhei.ttf")
        
    for index, effect in test_cases:
        item = AudioItem(index=index, text=f"Test {effect}", audio_path=audio_path, duration=2.0)
        size = CanvasSize(width=640, height=360)
        
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
            effect_duration=1.0,
        )
        
        idx, clip_path = _create_single_clip(
            item=item,
            size=size,
            settings=settings,
            clips_dir=out_dir,
            fps=30,
            tts_start_offset=0.0,
            logger=None,
        )
        print(f"Generated {effect} clip at {clip_path}")
        
        frame0 = out_dir / f"frame0_{effect}.png"
        frame1 = out_dir / f"frame1_{effect}.png"
        
        _run(["ffmpeg", "-y", "-ss", "00:00:00.1", "-i", str(clip_path), "-frames:v", "1", str(frame0)])
        _run(["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(clip_path), "-frames:v", "1", str(frame1)])
        
        with Image.open(frame0) as f0, Image.open(frame1) as f1:
            diff = ImageChops.difference(f0.convert('RGB'), f1.convert('RGB'))
            bbox = diff.getbbox()
            print(f"Effect {effect}: difference bounding box {bbox}")
            if bbox is None:
                raise ValueError(f"Effect {effect} showed no visual difference between t=0.1 and t=1.0!")
            
    print("All effects generated and showed visual animation.")

if __name__ == "__main__":
    main()
