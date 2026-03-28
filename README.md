# Vocal Analytics Service — AI Analysis Layer POC

## Proof of Concept: Call Recording → Structured Insights

This is a working proof of concept for **Building Block 2 (AI Analysis Layer)** of the StreamLine Call Analytics Platform. It accepts a call recording (audio file) or a transcript file, runs it through an AI pipeline, and returns structured analytical output.

> For the full system design covering all 4 building blocks, see [SYSTEM_DESIGN.md](./SYSTEM_DESIGN.md).

---

## Table of Contents

1. [What This POC Does](#what-this-poc-does)
2. [Quick Start](#quick-start-tldr)
3. [Technology Stack](#technology-stack)
4. [Machine Requirements](#machine-requirements)
5. [Setup & Installation](#setup--installation)
6. [LLM Provider Options](#llm-provider-options)
7. [API Reference](#api-reference)
8. [Input Formats & Validation](#input-formats--validation)
9. [Architecture Overview](#architecture-overview)
10. [AI Pipeline Design](#ai-pipeline-design)
11. [Prompt Design](#prompt-design)
12. [Structured Output Schema](#structured-output-schema)
13. [Handling Uncertainty & Incomplete Input](#handling-uncertainty--incomplete-input)
14. [Sample Requests & Responses](#sample-requests--responses)
15. [Project Structure](#project-structure)
16. [Testing](#testing)
17. [Assumptions](#assumptions)
18. [Limitations (POC vs Production)](#limitations-poc-vs-production)

---

## What This POC Does

Given a customer support call (as audio file or transcript file), this service extracts:

| Output | Description |
|--------|-------------|
| **Customer Issue** | What the customer called about, categorized with confidence score |
| **Resolution Status** | Whether the issue was resolved, and what action was taken |
| **Sentiment** | Customer sentiment at different points in the conversation (start, middle, end) with trajectory |
| **Key Themes** | Tags/topics identified in the conversation |
| **Pain Points** | Specific frustrations or problems voiced by the customer |
| **Flags** | Whether the AI is uncertain, input is incomplete, or manual review is needed |

---

## Quick Start (TL;DR)

```bash
# 1. Setup (one-time)
./setup.sh

# 2. Configure — set your OpenAI key in .env
#    Or set LLM_PROVIDER=ollama for local mode (no key needed)

# 3. Run
source .venv/bin/activate
python app.py

# 4. Test
curl -X POST http://localhost:8000/analyze \
  -F "file=@samples/sample_transcript.txt"

# 5. View API docs
open http://localhost:8000/docs
```

---

## Technology Stack

| Component | Choice | Version | Why |
|-----------|--------|---------|-----|
| Language | Python | 3.11+ | AI/ML ecosystem, FastAPI, Pydantic |
| API Framework | FastAPI | 0.115+ | Async, auto OpenAPI docs, file upload support, Pydantic integration |
| Validation | Pydantic | 2.x | Schema enforcement for LLM output, request/response models |
| Transcription | faster-whisper | 1.1+ | 4x faster than standard Whisper, runs on CPU, open-source |
| LLM (default) | OpenAI / Azure OpenAI | gpt-4o-mini | Best quality for structured JSON extraction |
| LLM (alternative) | Ollama (local) | llama3.1:8b | Fully offline, no API key, needs 8GB+ RAM |
| Audio processing | ffmpeg | system | Audio format conversion (required by Whisper) |
| ASGI Server | uvicorn | 0.30+ | Production-grade ASGI server |
| Testing | pytest + httpx | latest | Async test client for FastAPI |

### Key Libraries

```
fastapi>=0.115.0          # API framework
uvicorn>=0.30.0           # ASGI server
python-multipart>=0.0.9   # File upload support
pydantic>=2.0             # Schema validation
faster-whisper>=1.1.0     # Speech-to-text (CPU mode)
httpx>=0.27.0             # Async HTTP client
openai>=1.50.0            # OpenAI / Azure OpenAI SDK
python-dotenv>=1.0.0      # Environment variable management
```

---

## Machine Requirements

### With OpenAI API (recommended)

| Resource | Requirement |
|----------|-------------|
| CPU | 4+ cores (transcription is CPU-bound) |
| RAM | 4 GB (2 GB for app + 2 GB for Whisper `base` model) |
| Disk | 1 GB (Python + dependencies + Whisper model ~150 MB) |
| GPU | Not required (CPU inference, ~30-60s for a 5-min call) |
| Internet | Required (for OpenAI API calls) |
| OS | macOS, Linux, Windows (with WSL) |

### With Ollama (fully offline)

| Resource | Requirement |
|----------|-------------|
| CPU | 8+ cores recommended |
| RAM | **12 GB minimum** (2 GB app + 2 GB Whisper + 8 GB Ollama llama3.1:8b) |
| Disk | 6 GB (Python + Whisper model + Ollama model ~4.7 GB) |
| GPU | Optional (NVIDIA GPU with 8GB+ VRAM speeds up both) |
| Internet | **Not required** |
| OS | macOS, Linux, Windows (with WSL) |

### Whisper Model Size vs Performance (CPU, on a 5-minute call)

| Model | Size | RAM Usage | Processing Time (CPU) | English WER | Recommended For |
|-------|------|-----------|----------------------|-------------|-----------------|
| `tiny` | 75 MB | ~1 GB | ~15 sec | ~7.7% | Quick testing only |
| `base` | 150 MB | ~1.5 GB | ~30 sec | ~5.2% | **POC default** |
| `small` | 500 MB | ~2.5 GB | ~90 sec | ~3.9% | Better accuracy |
| `medium` | 1.5 GB | ~5 GB | ~300 sec | ~3.1% | High accuracy (slow on CPU) |

**POC default: `base`** — best balance of accuracy and speed for CPU inference. Automatically downloaded on first use (~150 MB).

---

## Setup & Installation

### Quick setup (recommended)

```bash
cd vocal-analytics-service
./setup.sh
```

The `setup.sh` script checks Python version (3.11+ required), checks for ffmpeg and Ollama, creates a virtual environment, installs dependencies, and creates `.env` from the template.

Then edit `.env` and set your `OPENAI_API_KEY`. For local-only mode, set `LLM_PROVIDER=ollama` instead (no key needed).

### Start the server

```bash
source .venv/bin/activate
python app.py
```

Server starts at:
- **API:** http://localhost:8000
- **Swagger docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

### Manual setup (if you prefer)

```bash
# 1. Check prerequisites
python3 --version   # Must be 3.11+
ffmpeg -version      # Required for audio files

# 2. Virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — set OPENAI_API_KEY (or LLM_PROVIDER=ollama for local mode)

# 5. Run
python app.py
```

---

## LLM Provider Options

The POC supports **2 LLM providers**:

### Option A: OpenAI API (Default)

| Detail | Value |
|--------|-------|
| Model | `gpt-4o-mini` (configurable via `OPENAI_MODEL` in .env) |
| Cost | ~$0.001 per call |
| Speed | ~100 tokens/sec |
| Quality | Best for structured JSON extraction |
| Setup | Get API key at [platform.openai.com](https://platform.openai.com) |

```bash
# In .env — direct OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your_key_here
OPENAI_MODEL=gpt-4o-mini

# Or Azure OpenAI — set the endpoint to auto-switch to Azure client
OPENAI_AZURE_API_ENDPOINT=https://your-resource.openai.azure.com
OPENAI_AZURE_API_VERSION=2024-12-01-preview
```

If `OPENAI_AZURE_API_ENDPOINT` is set, the service automatically uses the Azure OpenAI client. If not set, it uses the direct OpenAI API.

### Option B: Ollama Local (Free, fully offline)

| Detail | Value |
|--------|-------|
| Model | `llama3.1:8b` (configurable via `OLLAMA_MODEL` in .env) |
| Cost | **Free** (runs locally) |
| Speed | ~15-30 tokens/sec (CPU), ~60-100 tokens/sec (GPU) |
| Quality | Good for structured extraction, weaker on nuanced sentiment |
| RAM | ~8 GB for model (12 GB total with Whisper) |
| Disk | ~4.7 GB for model download |

**Step 1: Install Ollama**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

Ollama installs to `/usr/local/bin/ollama`. Models are stored in `~/.ollama/models/`.

**Step 2: Download the model and start the server**

```bash
ollama pull llama3.1:8b     # Download model (~4.7 GB, one-time)
ollama serve                # Start API server on localhost:11434
```

> `ollama serve` must be running in a separate terminal before starting the POC.
> Verify it's running: `curl http://localhost:11434` should return "Ollama is running".

**Step 3: Configure .env**

```bash
# In .env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1:8b
```

No API key needed — Ollama runs entirely on your machine.

### Provider Comparison

| Factor | OpenAI (Default) | Ollama (Local) |
|--------|-----------------|----------------|
| Cost | ~$0.001/call | Free |
| API key needed | Yes | No |
| Internet required | Yes | No |
| Setup time | 2 min (get key) | 5-10 min (install + download) |
| Response quality | Best | Good (8B model) |
| Speed | Fast (~2-3s) | Slow on CPU (~30-45s) |
| RAM needed | 4 GB | 12+ GB |

---

## API Reference

### `POST /analyze`

Upload a call recording or transcript file for analysis.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | Audio file (.wav, .mp3, .ogg, .flac, .m4a) or transcript file (.txt) |

**Constraints:**

| Constraint | Value |
|-----------|-------|
| Max file size | 50 MB |
| Supported audio formats | .wav, .mp3, .ogg, .flac, .m4a |
| Supported transcript format | .txt (plain text, UTF-8) |
| Min transcript length | 20 characters (shorter triggers `incomplete_input` flag) |

**Response:** `200 OK` — `application/json`

```json
{
  "call_id": "poc-a1b2c3d4",
  "status": "success",
  "processing_time_ms": 3200,
  "input_file": "call_recording.wav",
  "result_file": "results/2026-03-28/gpt-4o-mini/poc-a1b2c3d4-20260328_143200.json",
  "transcription": {
    "source": "audio",
    "model": "faster-whisper-base",
    "duration_seconds": 385,
    "confidence": 0.94,
    "text": "Agent: Thank you for calling StreamLine..."
  },
  "analysis": {
    "model_used": "gpt-4o-mini",
    "issue": {
      "primary_category": "billing",
      "sub_category": "duplicate_charge",
      "description": "Customer was charged twice for monthly subscription",
      "confidence": 0.95
    },
    "resolution": {
      "status": "resolved",
      "action_taken": "refund_initiated",
      "description": "Agent initiated refund for duplicate charge",
      "confidence": 0.92
    },
    "sentiment": {
      "overall": "negative_to_neutral",
      "trajectory": "improving",
      "score": -0.3,
      "segments": [
        {"phase": "opening", "sentiment": "frustrated", "score": -0.7},
        {"phase": "middle", "sentiment": "neutral", "score": -0.1},
        {"phase": "closing", "sentiment": "satisfied", "score": 0.5}
      ]
    },
    "themes": ["duplicate_billing", "refund_request", "subscription_management"],
    "pain_points": [
      "Customer discovered duplicate charge on their own",
      "Refund timeline of 5-7 days perceived as too long"
    ]
  },
  "flags": {
    "requires_manual_review": false,
    "incomplete_input": false,
    "low_confidence_fields": [],
    "ai_uncertainty_notes": null
  }
}
```

Each request also saves a detailed result file (including token usage) to the `results/` directory, organized by `date/model/`.


**Error responses:**

| Status | When |
|--------|------|
| `400 Bad Request` | Unsupported format, file too large, empty content |
| `422 Unprocessable Entity` | Audio could not be transcribed, LLM returned unparseable output |
| `503 Service Unavailable` | LLM provider unreachable, Whisper model not loaded |

### `GET /health`

```json
{
  "status": "healthy",
  "transcription_model": "faster-whisper-base",
  "llm_provider": "openai",
  "llm_model": "gpt-4o-mini"
}
```

---

## Input Formats & Validation

### Audio Files

| Validation | Rule | On Failure |
|-----------|------|-----------|
| File extension | Must be `.wav`, `.mp3`, `.ogg`, `.flac`, `.m4a` | 400: "Unsupported audio format" |
| File size | Max 50 MB | 400: "File too large (max 50MB)" |
| Audio integrity | Must be decodable by ffmpeg | 422: "Could not decode audio file" |
| Duration warning | > 30 minutes | Analysis proceeds but flags truncation note |

### Transcript Files (.txt)

| Validation | Rule | On Failure |
|-----------|------|-----------|
| Encoding | Must be valid UTF-8 | 400: "Invalid text encoding" |
| Length | Max 100,000 characters | 400: "Transcript too long" |
| Content | Not purely whitespace/punctuation | 400: "Transcript contains no usable content" |
| Short content | < 50 words | `flags.incomplete_input: true`, best-effort analysis |

---

## Architecture Overview

```
                         ┌──────────────────────────────┐
                         │         POST /analyze         │
                         │                              │
                         │  Upload: audio file (.wav,   │
                         │  .mp3, .ogg, .flac, .m4a)    │
                         │    OR                         │
                         │  Upload: transcript file      │
                         │  (.txt)                       │
                         └──────────────┬───────────────┘
                                        │
                              ┌─────────▼─────────┐
                              │  Input Validator   │
                              │                    │
                              │ • File type check  │
                              │ • Size limit (50MB)│
                              │ • Encoding check   │
                              └─────────┬──────────┘
                                        │
                          ┌─────────────┼──────────────┐
                          │ audio file  │              │ .txt file
                          ▼             │              ▼
               ┌──────────────────┐     │    ┌─────────────────┐
               │  Transcription   │     │    │  Transcript      │
               │  Module          │     │    │  Reader          │
               │                  │     │    │                  │
               │  faster-whisper  │     │    │  • UTF-8 decode  │
               │  (base model,   │     │    │  • Content check │
               │   CPU inference) │     │    │                  │
               └────────┬─────────┘     │    └────────┬────────┘
                        │               │             │
                        └───────────────┼─────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │  AI Analysis     │
                              │  Engine          │
                              │                  │
                              │  • Build prompt  │
                              │    with taxonomy │
                              │  • Call LLM API  │
                              │  • Parse JSON    │
                              │  • Validate      │
                              │    against schema│
                              │  • Score         │
                              │    confidence    │
                              │  • Flag          │
                              │    uncertainty   │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │  Structured      │
                              │  JSON Response   │
                              └──────────────────┘
```

---

## AI Pipeline Design

### Pipeline Stages

```
Stage 1: INPUT HANDLING
  ├── Audio path: validate → transcribe (faster-whisper) → get transcript
  └── Text path: validate → read file → normalize

Stage 2: TRANSCRIPT PREPARATION
  ├── Normalize whitespace and encoding
  ├── Detect if speaker labels present (Agent:/Customer:)
  ├── Estimate token count
  └── If > 12,000 tokens: truncate with note in flags

Stage 3: LLM ANALYSIS
  ├── Build system prompt (role, taxonomy, output schema)
  ├── Build user prompt (transcript + instructions)
  ├── Call LLM API with JSON mode
  ├── Parse response as JSON
  ├── Validate against Pydantic schema
  └── If parse fails: retry once with error correction prompt

Stage 4: POST-PROCESSING
  ├── Apply confidence score adjustments
  ├── Flag low-confidence fields (< 0.7)
  ├── Set requires_manual_review if uncertain
  ├── Set incomplete_input if transcript was too short
  └── Assemble final response
```

### Confidence Scoring Logic

| Condition | Effect |
|-----------|--------|
| Transcript < 50 words | All confidence scores capped at 0.5 |
| LLM returns "unknown" in any field | That field's confidence set to 0.3 |
| LLM JSON parse fails on first attempt | Retry; if second attempt succeeds, all confidence reduced by 0.1 |

---

## Prompt Design

### System Prompt

```
You are an expert customer service call analyst for StreamLine, a large consumer
services company. Your job is to analyze transcripts of customer support calls
and extract structured insights.

You must return a JSON object with exactly the following structure. Do not include
any text outside the JSON object.

IMPORTANT RULES:
1. Only use categories from this list: billing, service, account, product, complaint, general
2. Sub-categories must be specific and descriptive (e.g., "duplicate_charge", "plan_change")
3. Sentiment scores range from -1.0 (very negative) to 1.0 (very positive)
4. If you are uncertain about any field, set its confidence below 0.7
5. If the transcript is too short or unclear to determine a field, use "unknown" as the value
   and set confidence to 0.3
6. Never fabricate information — if the transcript doesn't mention something, don't invent it
7. Themes should be lowercase_snake_case tags
8. Pain points should be specific observations from the customer's perspective

OUTPUT SCHEMA:
{
  "issue": { ... },
  "resolution": { ... },
  "sentiment": { ... },
  "themes": [...],
  "pain_points": [...]
}
```

*(Full schema in [prompts.py](services/analysis/prompts.py))*

### Why This Prompt Design

| Decision | Reason |
|----------|--------|
| Categories are fixed list | Prevents LLM from inventing categories; matches `issue_categories` table in production |
| Confidence scores are explicit | Enables downstream filtering (< 0.7 = flag for review) |
| "Never fabricate" instruction | LLMs tend to hallucinate details — explicit instruction reduces this |
| Schema embedded in system prompt | Ensures consistent output structure across providers |
| 3-phase sentiment segments | Maps to opening/middle/closing of a call — consistent structure |

---

## Structured Output Schema

### Pydantic Models (enforced on LLM output)

```python
class Issue(BaseModel):
    primary_category: Literal["billing", "service", "account",
                              "product", "complaint", "general"]
    sub_category: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)

class Resolution(BaseModel):
    status: Literal["resolved", "unresolved", "escalated",
                    "partial", "unknown"]
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
    issue: Issue
    resolution: Resolution
    sentiment: Sentiment
    themes: list[str]
    pain_points: list[str]
```

If the LLM returns JSON that fails Pydantic validation:
1. **First attempt:** Retry with an error-correction prompt.
2. **Second failure:** Return 422 with `requires_manual_review: true` and the raw LLM output for debugging.

---

## Handling Uncertainty & Incomplete Input

| Scenario | Detection | Response |
|----------|-----------|----------|
| **Very short transcript** (< 50 words) | Word count check | `incomplete_input: true`, confidence capped at 0.5 |
| **Garbled/unintelligible audio** | Whisper confidence < 0.4 | `requires_manual_review: true`, best-effort transcript |
| **LLM returns "unknown" values** | Schema validation | Confidence set to 0.3, added to `low_confidence_fields` |
| **LLM JSON parse failure** | JSON parse error | Retry once; if fails again, return 422 with raw response |
| **LLM API timeout / error** | HTTP error | Return 503 with descriptive error |
| **Multiple issues in one call** | LLM detects > 1 issue | Primary issue returned; others noted in `themes` |
| **Audio too long (> 30 min)** | Duration check | Truncate, add `ai_uncertainty_notes` |

### Graceful Degradation

```
Best case:  Full analysis, all fields, high confidence
            ↓
            Partial analysis with low-confidence fields flagged
            ↓
Worst case: Error response with raw LLM output for debugging
```

---

## Sample Requests & Responses

### Example 1: Transcript file

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@samples/sample_transcript.txt"
```

**Response:**
```json
{
  "call_id": "poc-5116abc2",
  "status": "success",
  "processing_time_ms": 3680,
  "input_file": "sample_transcript.txt",
  "result_file": "results/2026-03-28/gpt-4o-mini/poc-5116abc2-20260328_110542.json",
  "transcription": {
    "source": "text",
    "model": null,
    "duration_seconds": null,
    "confidence": null,
    "text": "Agent: Thank you for calling StreamLine..."
  },
  "analysis": {
    "model_used": "gpt-4o-mini",
    "issue": {
      "primary_category": "billing",
      "sub_category": "duplicate_charge",
      "description": "The customer was charged twice for their subscription this month, which has happened before.",
      "confidence": 0.9
    },
    "resolution": {
      "status": "resolved",
      "action_taken": "processed a refund",
      "description": "The agent processed a refund for the duplicate charge and informed the customer about the expected processing time.",
      "confidence": 0.9
    },
    "sentiment": {
      "overall": "negative",
      "trajectory": "stable",
      "score": -0.5,
      "segments": [
        {"phase": "opening", "sentiment": "neutral", "score": 0.0},
        {"phase": "middle", "sentiment": "negative", "score": -0.7},
        {"phase": "closing", "sentiment": "neutral", "score": 0.0}
      ]
    },
    "themes": ["billing_issue", "customer_frustration"],
    "pain_points": [
      "duplicate charge on subscription",
      "long refund processing time"
    ]
  },
  "flags": {
    "requires_manual_review": false,
    "incomplete_input": false,
    "low_confidence_fields": [],
    "ai_uncertainty_notes": null
  }
}
```

### Example 2: Short transcript (edge case)

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@samples/sample_transcript_short.txt"
```

**Response:**
```json
{
  "call_id": "poc-f1af21f3",
  "status": "partial",
  "processing_time_ms": 2512,
  "input_file": "sample_transcript_short.txt",
  "result_file": "results/2026-03-28/gpt-4o-mini/poc-f1af21f3-20260328_110600.json",
  "analysis": {
    "model_used": "gpt-4o-mini",
    "issue": {
      "primary_category": "service",
      "sub_category": "internet_outage",
      "description": "The customer reported that their internet is not working.",
      "confidence": 0.50
    },
    "resolution": {
      "status": "unknown",
      "action_taken": "none",
      "description": "The resolution status is unclear as the transcript does not provide further details.",
      "confidence": 0.30
    }
  },
  "flags": {
    "requires_manual_review": true,
    "incomplete_input": true,
    "low_confidence_fields": ["issue.confidence", "resolution.confidence", "resolution.status", "sentiment.segments"],
    "ai_uncertainty_notes": "Transcript is very short (6 words). Analysis is best-effort with low confidence."
  }
}
```

### Example 3: Audio file

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@path/to/call_recording.wav"
```

---

## Project Structure

```
vocal-analytics-service/
├── app.py                              # Entry point — run: python app.py
├── setup.sh                            # One-time setup script
├── README.md                           # This file
├── SYSTEM_DESIGN.md                    # Full system design (Part 1)
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment variable template
├── pyproject.toml                      # Project metadata
│
├── services/
│   └── analysis/                       # AI Analysis Service (POC)
│       ├── main.py                     # FastAPI app: /analyze and /health
│       ├── config.py                   # Settings from .env (dotenv + pydantic-settings)
│       ├── schemas.py                  # Pydantic models (request/response/LLM output)
│       ├── transcriber.py             # Faster-Whisper integration
│       ├── analyzer.py                # LLM orchestration: prompt → parse → validate
│       ├── prompts.py                 # System and user prompt templates
│       ├── validators.py             # Input validation (file type, size, encoding)
│       └── llm/
│           ├── base.py                # Abstract LLM client + LLMResponse dataclass
│           ├── openai_client.py       # OpenAI / Azure OpenAI client (auto-detects)
│           └── ollama_client.py       # Ollama local client
│
├── results/                            # Analysis output (auto-created)
│   └── <date>/                        # e.g., 2026-03-28/
│       └── <model>/                   # e.g., gpt-4o-mini/
│           └── poc-<id>-<ts>.json     # Full result + token usage
│
├── tests/
│   ├── test_analyze_endpoint.py       # API endpoint tests
│   ├── test_analyzer.py               # LLM analysis tests (mocked)
│   ├── test_validators.py            # Input validation tests
│   ├── test_schemas.py               # Pydantic schema tests
│   └── fixtures/
│       └── golden_analysis.json       # Expected output for validation
│
└── samples/                            # Sample files for manual testing
    ├── sample_transcript.txt           # Billing dispute transcript
    ├── sample_transcript_short.txt     # Very short transcript (edge case)
    └── sample_transcript_multi.txt     # Multi-issue transcript (edge case)
```

---

## Testing

```bash
source .venv/bin/activate

# Run all tests (mocked LLM, no API key needed)
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=services/analysis --cov-report=term-missing
```

| Test File | What It Tests | Needs API Key? |
|-----------|---------------|----------------|
| `test_validators.py` | File type checks, size limits, encoding | No |
| `test_schemas.py` | Pydantic model validation, edge cases | No |
| `test_analyzer.py` | Prompt building, JSON parsing, confidence scoring (mocked LLM) | No |
| `test_analyze_endpoint.py` | Full API request/response cycle (mocked LLM) | No |

---

## Assumptions

1. **Single-request processing**: No queuing or batch processing. One file at a time.
2. **Results persisted locally**: Each analysis is saved to `results/<date>/<model>/` as JSON (includes token usage, timestamps).
3. **No authentication**: API is open (local development use only).
4. **English only**: Transcription and analysis assume English language input.
5. **Two-party calls**: Transcripts are between one customer and one agent.
6. **Whisper model download**: The `base` model (~150 MB) downloads automatically on first audio request.

### Design Decisions

| Decision | Why |
|----------|-----|
| FastAPI over Flask | Native async, auto-generated docs, Pydantic integration, file upload support |
| OpenAI as default LLM | Best quality for structured JSON extraction; model configurable via .env |
| Ollama as alternative | Free, fully offline fallback for environments without API keys |
| faster-whisper over whisper | 4x faster on CPU, same accuracy, lower RAM |
| `base` Whisper model | Best accuracy/speed balance for CPU; `tiny` too inaccurate, `small` too slow |
| Pydantic validation of LLM output | Catches malformed output, enforces types, clear error messages |
| Retry on parse failure | LLMs occasionally produce malformed JSON; one retry usually fixes it |

---

## Limitations (POC vs Production)

| Area | POC Limitation | Production Solution (see SYSTEM_DESIGN.md) |
|------|---------------|---------------------------------------------|
| **Scale** | Single request, synchronous | Queue-based async pipeline, 20K calls/day |
| **Transcription** | CPU-based, `base` model (~5% WER) | GPU-based, `large-v3` model (~1% WER) |
| **LLM** | OpenAI/Azure or Ollama (manual switch) | Tiered (GPT-4o-mini + GPT-4o), auto-failover |
| **Storage** | Local JSON files in `results/` | PostgreSQL + Elasticsearch + S3 |
| **Auth** | None | JWT + RBAC |
| **SOP Compliance** | Not included | Hybrid rule engine + LLM judge |
| **Issue Categories** | Fixed list in prompt | Dynamic from `issue_categories` DB table |
| **Monitoring** | Console logs | CloudWatch + Grafana dashboards |

---

*For the complete system architecture, see [SYSTEM_DESIGN.md](./SYSTEM_DESIGN.md).*
