"""AI analysis engine: orchestrates LLM calls, parsing, validation, and confidence scoring."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from services.analysis.config import settings
from services.analysis.llm import get_llm_client
from services.analysis.llm.base import BaseLLMClient, LLMResponse
from services.analysis.prompts import (
    RETRY_PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from services.analysis.schemas import AnalysisResult, Flags

logger = logging.getLogger(__name__)


@dataclass
class AnalysisOutput:
    result: AnalysisResult
    model_used: str
    input_tokens: int = 0
    output_tokens: int = 0
    flags: Flags = field(default_factory=Flags)
    raw_response: str | None = None


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    # Strip ```json ... ``` wrappers
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _count_words(text: str) -> int:
    return len(text.split())


def _apply_confidence_caps(
    result: AnalysisResult, word_count: int, has_speaker_labels: bool
) -> tuple[AnalysisResult, list[str]]:
    """Apply confidence adjustments based on transcript quality.

    Returns the modified result and list of low-confidence field names.
    """
    low_fields: list[str] = []
    data = result.model_dump()

    # Short transcript: cap all confidence at 0.5
    if word_count < settings.short_transcript_threshold:
        for section in ("issue", "resolution"):
            if data[section]["confidence"] > 0.5:
                data[section]["confidence"] = 0.5

    # Check for "unknown" values
    if data["issue"]["primary_category"] == "general" and data["issue"]["sub_category"] == "unknown":
        data["issue"]["confidence"] = min(data["issue"]["confidence"], 0.3)
    if data["resolution"]["status"] == "unknown":
        data["resolution"]["confidence"] = min(data["resolution"]["confidence"], 0.3)

    # Collect low-confidence fields
    if data["issue"]["confidence"] < 0.7:
        low_fields.append("issue.confidence")
    if data["resolution"]["confidence"] < 0.7:
        low_fields.append("resolution.confidence")
        low_fields.append("resolution.status")

    # Check sentiment segments for unknowns
    for seg in data["sentiment"]["segments"]:
        if seg["sentiment"] == "unknown":
            low_fields.append("sentiment.segments")
            break

    return AnalysisResult.model_validate(data), low_fields


def _detect_speaker_labels(transcript: str) -> bool:
    """Check if the transcript has speaker labels."""
    lower = transcript[:500].lower()
    return any(
        label in lower
        for label in ("agent:", "customer:", "representative:", "caller:",
                      "speaker 1:", "speaker 2:", "agent :", "customer :")
    )


async def analyze_transcript(
    transcript: str,
    llm_client: BaseLLMClient | None = None,
) -> AnalysisOutput:
    """Run the full analysis pipeline on a transcript.

    1. Build prompts
    2. Call LLM
    3. Parse JSON
    4. Validate with Pydantic
    5. Apply confidence adjustments
    6. Generate flags
    """
    if llm_client is None:
        llm_client = get_llm_client()

    word_count = _count_words(transcript)
    has_speaker_labels = _detect_speaker_labels(transcript)

    # Truncate very long transcripts (keep first ~12K tokens ≈ 9K words)
    truncated = False
    if word_count > 9000:
        words = transcript.split()
        transcript = " ".join(words[:9000])
        truncated = True

    # Build prompts
    user_prompt = USER_PROMPT_TEMPLATE.format(transcript=transcript)

    # Call LLM
    llm_resp = await llm_client.chat(SYSTEM_PROMPT, user_prompt)
    total_input_tokens = llm_resp.input_tokens
    total_output_tokens = llm_resp.output_tokens

    # Parse JSON
    result, parse_error = _try_parse(llm_resp.text)

    # Retry once on parse failure
    if result is None and settings.max_llm_retries > 0:
        logger.warning("LLM parse failed (%s), retrying...", parse_error)
        retry_prompt = RETRY_PROMPT_TEMPLATE.format(error=parse_error)
        llm_resp = await llm_client.chat(SYSTEM_PROMPT, retry_prompt)
        total_input_tokens += llm_resp.input_tokens
        total_output_tokens += llm_resp.output_tokens
        result, parse_error = _try_parse(llm_resp.text)

    if result is None:
        raise AnalysisParseError(
            f"Failed to parse LLM output after retries: {parse_error}",
            raw_response=llm_resp.text,
        )

    # Apply confidence adjustments
    result, low_fields = _apply_confidence_caps(result, word_count, has_speaker_labels)

    # Build flags
    flags = Flags(
        incomplete_input=word_count < settings.short_transcript_threshold,
        low_confidence_fields=low_fields,
        requires_manual_review=(
            word_count < settings.min_transcript_words
            or len(low_fields) >= 2
        ),
    )

    # Truncation note
    notes: list[str] = []
    if truncated:
        notes.append("Transcript was truncated to ~9000 words for analysis.")
    if word_count < settings.short_transcript_threshold:
        notes.append(
            f"Transcript is very short ({word_count} words). "
            "Analysis is best-effort with low confidence."
        )
    if notes:
        flags.ai_uncertainty_notes = " ".join(notes)

    return AnalysisOutput(
        result=result,
        model_used=llm_client.model_name(),
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        flags=flags,
        raw_response=llm_resp.text,
    )


def _try_parse(raw: str) -> tuple[AnalysisResult | None, str | None]:
    """Try to parse raw LLM text as AnalysisResult."""
    try:
        cleaned = _extract_json(raw)
        data = json.loads(cleaned)
        return AnalysisResult.model_validate(data), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except ValidationError as e:
        return None, f"Schema validation failed: {e}"
    except Exception as e:
        return None, f"Unexpected error: {e}"


class AnalysisParseError(Exception):
    """Raised when LLM output cannot be parsed after retries."""

    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response
