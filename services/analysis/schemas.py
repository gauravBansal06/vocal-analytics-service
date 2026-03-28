"""Pydantic models for request validation, LLM output parsing, and API responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# LLM output models (parsed from LLM JSON response)
# ---------------------------------------------------------------------------

class Issue(BaseModel):
    primary_category: Literal[
        "billing", "service", "account", "product", "complaint", "general"
    ]
    sub_category: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)


class Resolution(BaseModel):
    status: Literal["resolved", "unresolved", "escalated", "partial", "unknown"]
    action_taken: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)


class SentimentSegment(BaseModel):
    phase: Literal["opening", "middle", "closing"]
    sentiment: str
    score: float = Field(ge=-1.0, le=1.0)


class Sentiment(BaseModel):
    overall: str
    trajectory: Literal["improving", "worsening", "stable"]
    score: float = Field(ge=-1.0, le=1.0)
    segments: list[SentimentSegment]


class AnalysisResult(BaseModel):
    """Schema enforced on LLM JSON output."""

    issue: Issue
    resolution: Resolution
    sentiment: Sentiment
    themes: list[str]
    pain_points: list[str]


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------

class TranscriptionInfo(BaseModel):
    source: Literal["audio", "text"]
    model: str | None = None
    duration_seconds: float | None = None
    confidence: float | None = None
    text: str


class Flags(BaseModel):
    requires_manual_review: bool = False
    incomplete_input: bool = False
    low_confidence_fields: list[str] = Field(default_factory=list)
    ai_uncertainty_notes: str | None = None


class AnalysisWithModel(BaseModel):
    model_used: str
    issue: Issue
    resolution: Resolution
    sentiment: Sentiment
    themes: list[str]
    pain_points: list[str]


class AnalyzeResponse(BaseModel):
    call_id: str
    status: Literal["success", "partial", "error"]
    processing_time_ms: int
    input_file: str | None = None
    result_file: str | None = None
    transcription: TranscriptionInfo
    analysis: AnalysisWithModel
    flags: Flags


class ErrorResponse(BaseModel):
    detail: str
    call_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    transcription_model: str
    llm_provider: str
    llm_model: str
