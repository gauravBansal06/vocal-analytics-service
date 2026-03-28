"""Tests for the /analyze API endpoint."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from services.analysis.main import app

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "golden_analysis.json").read_text())
SAMPLES = Path(__file__).parent.parent / "samples"


def _mock_analyze(*args, **kwargs):
    """Return a mock AnalysisOutput."""
    from services.analysis.analyzer import AnalysisOutput
    from services.analysis.schemas import AnalysisResult, Flags

    return AnalysisOutput(
        result=AnalysisResult.model_validate(GOLDEN),
        model_used="mock-model",
        flags=Flags(),
    )


@pytest.fixture
def mock_analyzer():
    with patch("services.analysis.main.analyze_transcript", new_callable=AsyncMock) as m:
        m.side_effect = _mock_analyze
        yield m


@pytest.mark.asyncio
async def test_health(mock_analyzer):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_analyze_with_transcript_file(mock_analyzer):
    content = (SAMPLES / "sample_transcript.txt").read_bytes()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/analyze",
            files={"file": ("transcript.txt", content, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["analysis"]["issue"]["primary_category"] == "billing"
        assert data["call_id"].startswith("poc-")



@pytest.mark.asyncio
async def test_no_file_returns_422(mock_analyzer):
    """FastAPI returns 422 when required file field is missing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/analyze")
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unsupported_file_format(mock_analyzer):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/analyze",
            files={"file": ("file.pdf", b"fake content", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_empty_transcript_file_returns_400(mock_analyzer):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/analyze",
            files={"file": ("empty.txt", b"   ", "text/plain")},
        )
        assert resp.status_code == 400
