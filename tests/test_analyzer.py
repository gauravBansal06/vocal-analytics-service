"""Tests for the analyzer engine with mocked LLM."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from services.analysis.analyzer import AnalysisParseError, analyze_transcript
from services.analysis.llm.base import BaseLLMClient, LLMResponse

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "golden_analysis.json").read_text())


def _make_mock_client(response: str | dict, model: str = "mock-model") -> BaseLLMClient:
    """Create a mock LLM client that returns a fixed LLMResponse."""
    client = AsyncMock(spec=BaseLLMClient)
    if isinstance(response, dict):
        response = json.dumps(response)
    client.chat.return_value = LLMResponse(text=response, input_tokens=100, output_tokens=50)
    client.model_name.return_value = model
    return client


@pytest.mark.asyncio
async def test_valid_analysis():
    client = _make_mock_client(GOLDEN)
    result = await analyze_transcript(
        "Agent: Hi. Customer: I was charged twice. Agent: I will refund you.",
        llm_client=client,
    )
    assert result.result.issue.primary_category == "billing"
    assert result.model_used == "mock-model"


@pytest.mark.asyncio
async def test_short_transcript_flags():
    client = _make_mock_client(GOLDEN)
    result = await analyze_transcript(
        "Customer: Help.",
        llm_client=client,
    )
    assert result.flags.incomplete_input is True
    # Confidence should be capped at 0.5 for short transcripts
    assert result.result.issue.confidence <= 0.5


@pytest.mark.asyncio
async def test_json_in_markdown_fences():
    """LLM sometimes wraps JSON in ```json ... ```."""
    wrapped = f"```json\n{json.dumps(GOLDEN)}\n```"
    client = _make_mock_client(wrapped)
    result = await analyze_transcript(
        "Agent: Hi. Customer: My bill is wrong. Agent: Let me check.",
        llm_client=client,
    )
    assert result.result.issue.primary_category == "billing"


@pytest.mark.asyncio
async def test_invalid_json_retries():
    """First call returns garbage, second returns valid JSON."""
    client = AsyncMock(spec=BaseLLMClient)
    client.chat.side_effect = [
        LLMResponse(text="This is not JSON at all", input_tokens=100, output_tokens=10),
        LLMResponse(text=json.dumps(GOLDEN), input_tokens=100, output_tokens=50),
    ]
    client.model_name.return_value = "mock-model"

    result = await analyze_transcript(
        "Agent: Hi. Customer: My bill is wrong.",
        llm_client=client,
    )
    assert client.chat.call_count == 2
    assert result.result.issue.primary_category == "billing"


@pytest.mark.asyncio
async def test_permanent_parse_failure_raises():
    """Both attempts return garbage → should raise AnalysisParseError."""
    client = AsyncMock(spec=BaseLLMClient)
    client.chat.return_value = LLMResponse(text="not json", input_tokens=100, output_tokens=10)
    client.model_name.return_value = "mock-model"

    with pytest.raises(AnalysisParseError):
        await analyze_transcript(
            "Agent: Hello. Customer: Help me.",
            llm_client=client,
        )


@pytest.mark.asyncio
async def test_unknown_resolution_lowers_confidence():
    data = GOLDEN.copy()
    data = json.loads(json.dumps(GOLDEN))  # deep copy
    data["resolution"]["status"] = "unknown"
    data["resolution"]["confidence"] = 0.9

    client = _make_mock_client(data)
    result = await analyze_transcript(
        "Agent: Hi. Customer: My service is down. Agent: Let me check.",
        llm_client=client,
    )
    assert result.result.resolution.confidence <= 0.3
    assert "resolution.confidence" in result.flags.low_confidence_fields


@pytest.mark.asyncio
async def test_speaker_label_detection():
    """Transcript with speaker labels should be detected."""
    client = _make_mock_client(GOLDEN)
    result = await analyze_transcript(
        "Agent: Hello, how can I help?\nCustomer: I need to cancel my plan.\nAgent: I can help with that.",
        llm_client=client,
    )
    # Should succeed without issues
    assert result.result is not None
