"""Audio transcription using faster-whisper."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from services.analysis.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded whisper model (heavy import, loaded on first use)
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        logger.info(
            "Loading Whisper model '%s' (device=%s, compute_type=%s)...",
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("Whisper model loaded.")
    return _model


@dataclass
class TranscriptionResult:
    text: str
    duration_seconds: float
    confidence: float
    language: str


def transcribe_audio(audio_bytes: bytes, filename: str) -> TranscriptionResult:
    """Transcribe audio bytes using faster-whisper.

    Writes to a temp file since faster-whisper needs a file path.
    """
    suffix = Path(filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()

        model = _get_model()
        segments, info = model.transcribe(
            tmp.name,
            beam_size=5,
            language="en",
            vad_filter=True,  # Skip silence
        )

        # Collect all segments
        all_segments = list(segments)

        if not all_segments:
            return TranscriptionResult(
                text="",
                duration_seconds=info.duration,
                confidence=0.0,
                language=info.language or "en",
            )

        full_text = " ".join(seg.text.strip() for seg in all_segments)
        avg_confidence = (
            sum(seg.avg_log_prob for seg in all_segments) / len(all_segments)
        )
        # Convert log prob to a 0-1 confidence (approximate)
        # avg_log_prob is typically between -1.0 and 0.0
        confidence = max(0.0, min(1.0, 1.0 + avg_confidence))

        return TranscriptionResult(
            text=full_text,
            duration_seconds=info.duration,
            confidence=round(confidence, 3),
            language=info.language or "en",
        )
