"""Input validation for file uploads and transcript text."""

from __future__ import annotations

from fastapi import UploadFile

from services.analysis.config import settings

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
TRANSCRIPT_EXTENSIONS = {".txt", ".json"}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | TRANSCRIPT_EXTENSIONS


def get_file_extension(filename: str) -> str:
    """Return lowercased file extension including the dot."""
    dot_idx = filename.rfind(".")
    if dot_idx == -1:
        return ""
    return filename[dot_idx:].lower()


def validate_file_extension(filename: str) -> str | None:
    """Return an error message if the extension is not supported, else None."""
    ext = get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return (
            f"Unsupported file format '{ext}'. "
            f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return None


def is_audio_file(filename: str) -> bool:
    return get_file_extension(filename) in AUDIO_EXTENSIONS


def is_transcript_file(filename: str) -> bool:
    return get_file_extension(filename) in TRANSCRIPT_EXTENSIONS


async def validate_file_size(file: UploadFile) -> str | None:
    """Check file size without reading entire file into memory.

    Returns error message or None.
    """
    # Read content to check size (FastAPI UploadFile is spooled)
    content = await file.read()
    await file.seek(0)  # Reset for subsequent reads
    if len(content) > settings.max_file_size_bytes:
        return f"File too large ({len(content) // (1024*1024)}MB). Max: {settings.max_file_size_mb}MB"
    return None


def validate_transcript_text(text: str) -> str | None:
    """Validate raw transcript text. Returns error message or None."""
    if not text or not text.strip():
        return "Transcript is empty"
    if len(text) > settings.max_transcript_chars:
        return f"Transcript too long ({len(text)} chars). Max: {settings.max_transcript_chars}"
    stripped = text.strip()
    # Check it's not purely punctuation/whitespace
    alpha_count = sum(1 for c in stripped if c.isalpha())
    if alpha_count < 5:
        return "Transcript contains no usable content"
    return None
