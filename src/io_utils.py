from __future__ import annotations

from datetime import datetime
from pathlib import Path

from models import CanvasSize, OutputMode


def read_text_input(text: str | None, text_file: str | None) -> str:
    if text:
        return text
    if text_file:
        return Path(text_file).read_text(encoding="utf-8")
    raise ValueError("Either --text or --text-file is required.")


def parse_output_modes(raw: str) -> list[OutputMode]:
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("--output-modes cannot be empty.")
    allowed = {"portrait", "landscape"}
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise ValueError(f"Invalid output mode(s): {', '.join(invalid)}")
    ordered: list[OutputMode] = []
    seen: set[str] = set()
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)  # type: ignore[arg-type]
    return ordered


def parse_size(raw: str, argument_name: str) -> CanvasSize:
    value = raw.lower().strip()
    if "x" not in value:
        raise ValueError(f"{argument_name} must be WIDTHxHEIGHT, got: {raw}")
    width_raw, height_raw = value.split("x", 1)
    try:
        width = int(width_raw)
        height = int(height_raw)
    except ValueError as exc:
        raise ValueError(f"{argument_name} must be WIDTHxHEIGHT, got: {raw}") from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"{argument_name} width/height must be > 0")
    return CanvasSize(width=width, height=height)


def prepare_output_dirs(work_dir: Path) -> dict[str, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = work_dir / f"run_{ts}"
    paths = {
        "run_dir": run_dir,
        "sentences_dir": run_dir / "01_sentences",
        "images_dir": run_dir / "02_images",
        "audio_dir": run_dir / "03_audio",
        "segments_dir": run_dir / "04_segments",
        "final_dir": run_dir / "05_final",
        "logs_dir": run_dir / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
