"""Tests for Pydantic schema validation."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.analysis.schemas import AnalysisResult, Issue, Resolution, Sentiment, SentimentSegment


FIXTURES = Path(__file__).parent / "fixtures"


class TestAnalysisResult:
    def test_golden_output_parses(self):
        """The golden test fixture must parse without errors."""
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        result = AnalysisResult.model_validate(data)
        assert result.issue.primary_category == "billing"
        assert result.resolution.status == "resolved"
        assert len(result.sentiment.segments) == 3

    def test_invalid_category_rejected(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        data["issue"]["primary_category"] = "invalid_category"
        with pytest.raises(ValidationError):
            AnalysisResult.model_validate(data)

    def test_invalid_resolution_status_rejected(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        data["resolution"]["status"] = "maybe"
        with pytest.raises(ValidationError):
            AnalysisResult.model_validate(data)

    def test_confidence_out_of_range(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        data["issue"]["confidence"] = 1.5
        with pytest.raises(ValidationError):
            AnalysisResult.model_validate(data)

    def test_sentiment_score_out_of_range(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        data["sentiment"]["score"] = -2.0
        with pytest.raises(ValidationError):
            AnalysisResult.model_validate(data)

    def test_invalid_trajectory_rejected(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        data["sentiment"]["trajectory"] = "sideways"
        with pytest.raises(ValidationError):
            AnalysisResult.model_validate(data)

    def test_missing_required_field(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        del data["issue"]
        with pytest.raises(ValidationError):
            AnalysisResult.model_validate(data)

    def test_empty_themes_ok(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        data["themes"] = []
        result = AnalysisResult.model_validate(data)
        assert result.themes == []

    def test_empty_pain_points_ok(self):
        data = json.loads((FIXTURES / "golden_analysis.json").read_text())
        data["pain_points"] = []
        result = AnalysisResult.model_validate(data)
        assert result.pain_points == []
