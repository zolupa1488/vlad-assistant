"""Local Whisper transcription via faster-whisper.

Runs on CPU with int8 quantization, fast enough for short voice notes (≤2 min).
Model is downloaded once on first call and cached under /app/cache/whisper.
"""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache

from loguru import logger

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
WHISPER_CACHE_DIR = os.environ.get("WHISPER_CACHE_DIR", "/app/cache/whisper")


@lru_cache(maxsize=1)
def _get_model():
    # Lazy import — avoids pulling in CTranslate2 at module load time when whisper isn't used.
    from faster_whisper import WhisperModel

    logger.info(
        "Loading Whisper model={} device={} compute={} cache={}",
        WHISPER_MODEL,
        WHISPER_DEVICE,
        WHISPER_COMPUTE,
        WHISPER_CACHE_DIR,
    )
    os.makedirs(WHISPER_CACHE_DIR, exist_ok=True)
    return WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE,
        download_root=WHISPER_CACHE_DIR,
    )


def _sync_transcribe(audio_path: str, language: str | None) -> str:
    model = _get_model()
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=1,
        vad_filter=True,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    logger.info(
        "voice transcribed: lang={} duration={:.1f}s text_len={}",
        info.language,
        info.duration,
        len(text),
    )
    return text


async def transcribe_file(audio_path: str, language: str | None = "ru") -> str:
    """Transcribe an audio file (any format ffmpeg understands). Returns plain text."""
    return await asyncio.to_thread(_sync_transcribe, audio_path, language)
