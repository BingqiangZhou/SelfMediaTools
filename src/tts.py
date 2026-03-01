from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import edge_tts

from ffmpeg_utils import probe_duration
from models import AudioItem, numbered_name

MAX_TTS_RETRIES = 3


def _default_tts_workers() -> int:
    cpu = os.cpu_count() or 4
    return max(1, min(8, cpu))


async def _synthesize_sentence(
    text: str,
    out_path: Path,
    voice: str,
    rate: str,
    volume: str,
) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
    await communicate.save(str(out_path))


async def _synthesize_with_retry(
    index: int,
    sentence: str,
    audio_dir: Path,
    voice: str,
    rate: str,
    volume: str,
    logger: logging.Logger | None,
) -> AudioItem:
    audio_path = audio_dir / numbered_name(index, "mp3")
    last_exc: Exception | None = None
    for attempt in range(1, MAX_TTS_RETRIES + 1):
        try:
            if audio_path.exists():
                audio_path.unlink()
            await _synthesize_sentence(
                text=sentence,
                out_path=audio_path,
                voice=voice,
                rate=rate,
                volume=volume,
            )
            duration = await asyncio.to_thread(probe_duration, audio_path, logger)
            if logger:
                logger.info("tts generated: #%03d %.3fs", index, duration)
            return AudioItem(
                index=index,
                text=sentence,
                audio_path=audio_path.resolve(),
                duration=duration,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if logger:
                logger.warning(
                    "tts failed #%03d attempt=%d/%d: %s",
                    index,
                    attempt,
                    MAX_TTS_RETRIES,
                    exc,
                )
            if audio_path.exists():
                audio_path.unlink()
            if attempt < MAX_TTS_RETRIES:
                await asyncio.sleep(float(attempt))

    raise RuntimeError(f"TTS failed after {MAX_TTS_RETRIES} attempts for sentence #{index}") from last_exc


async def _generate_tts_async(
    sentences: list[str],
    audio_dir: Path,
    voice: str,
    rate: str,
    volume: str,
    logger: logging.Logger | None,
    max_workers: int,
) -> list[AudioItem]:
    semaphore = asyncio.Semaphore(max_workers)

    async def _worker(index: int, sentence: str) -> AudioItem:
        async with semaphore:
            return await _synthesize_with_retry(
                index=index,
                sentence=sentence,
                audio_dir=audio_dir,
                voice=voice,
                rate=rate,
                volume=volume,
                logger=logger,
            )

    tasks = [
        asyncio.create_task(_worker(index, sentence))
        for index, sentence in enumerate(sentences, start=1)
    ]
    items = await asyncio.gather(*tasks)
    items.sort(key=lambda item: item.index)
    return items


def generate_tts(
    sentences: list[str],
    audio_dir: Path,
    voice: str,
    rate: str,
    volume: str,
    logger: logging.Logger | None = None,
    max_workers: int | None = None,
) -> list[AudioItem]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    workers = max_workers or _default_tts_workers()
    if workers <= 0:
        raise ValueError("max_workers for TTS must be > 0")
    return asyncio.run(
        _generate_tts_async(
            sentences=sentences,
            audio_dir=audio_dir,
            voice=voice,
            rate=rate,
            volume=volume,
            logger=logger,
            max_workers=workers,
        )
    )
