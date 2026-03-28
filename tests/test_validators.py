"""Tests for input validation logic."""

import pytest

from services.analysis.validators import (
    get_file_extension,
    is_audio_file,
    is_transcript_file,
    validate_file_extension,
    validate_transcript_text,
)


class TestFileExtension:
    def test_wav(self):
        assert get_file_extension("call.wav") == ".wav"

    def test_uppercase(self):
        assert get_file_extension("CALL.MP3") == ".mp3"

    def test_no_extension(self):
        assert get_file_extension("noext") == ""

    def test_multiple_dots(self):
        assert get_file_extension("my.call.recording.ogg") == ".ogg"


class TestValidateFileExtension:
    def test_supported_audio(self):
        for ext in [".wav", ".mp3", ".ogg", ".flac", ".m4a"]:
            assert validate_file_extension(f"file{ext}") is None

    def test_supported_transcript(self):
        assert validate_file_extension("transcript.txt") is None
        assert validate_file_extension("transcript.json") is None

    def test_unsupported(self):
        err = validate_file_extension("file.pdf")
        assert err is not None
        assert "Unsupported" in err

    def test_no_extension(self):
        err = validate_file_extension("noext")
        assert err is not None


class TestIsAudioFile:
    def test_audio(self):
        assert is_audio_file("call.wav") is True
        assert is_audio_file("call.mp3") is True

    def test_not_audio(self):
        assert is_audio_file("transcript.txt") is False
        assert is_audio_file("data.json") is False


class TestIsTranscriptFile:
    def test_transcript(self):
        assert is_transcript_file("transcript.txt") is True
        assert is_transcript_file("data.json") is True

    def test_not_transcript(self):
        assert is_transcript_file("call.wav") is False


class TestValidateTranscriptText:
    def test_valid(self):
        assert validate_transcript_text("Customer: Hi, I need help with my bill.") is None

    def test_empty(self):
        assert validate_transcript_text("") is not None
        assert validate_transcript_text("   ") is not None

    def test_too_long(self):
        text = "a " * 60_000
        err = validate_transcript_text(text)
        assert err is not None
        assert "too long" in err

    def test_no_usable_content(self):
        err = validate_transcript_text("... !!!")
        assert err is not None
        assert "no usable content" in err

    def test_short_but_valid(self):
        # Short but has alpha content
        assert validate_transcript_text("Help me") is None
