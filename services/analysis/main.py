"""FastAPI application — AI Analysis Layer POC."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from services.analysis.analyzer import AnalysisParseError, analyze_transcript
from services.analysis.config import settings
from services.analysis.schemas import (
    AnalysisWithModel,
    AnalyzeResponse,
    ErrorResponse,
    Flags,
    HealthResponse,
    TranscriptionInfo,
)
from services.analysis.transcriber import transcribe_audio
from services.analysis.validators import (
    is_audio_file,
    is_transcript_file,
    validate_file_extension,
    validate_file_size,
    validate_transcript_text,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Vocal Analytics — AI Analysis POC",
    description="Accepts a call recording or transcript and returns structured analysis.",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        transcription_model=f"faster-whisper-{settings.whisper_model}",
        llm_provider=settings.llm_provider,
        llm_model=settings.active_llm_model,
    )


@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def analyze(
    file: UploadFile = File(...),
):
    """Analyze a call recording or transcript file.

    Upload a file:
    - Audio: .wav, .mp3, .ogg, .flac, .m4a
    - Transcript: .txt (plain text), .json (structured segments)
    """
    call_id = f"poc-{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    # --- Input validation ---
    if not file.filename:
        raise HTTPException(400, "A file must be uploaded.")

    # Validate extension
    ext_err = validate_file_extension(file.filename)
    if ext_err:
        raise HTTPException(400, ext_err)

    # Validate size
    size_err = await validate_file_size(file)
    if size_err:
        raise HTTPException(400, size_err)

    content = await file.read()

    transcript_text: str = ""
    transcription_info: TranscriptionInfo | None = None

    if is_audio_file(file.filename):
        # Transcribe audio
        try:
            result = transcribe_audio(content, file.filename)
        except Exception as e:
            logger.exception("Transcription failed for %s", call_id)
            raise HTTPException(422, f"Could not transcribe audio: {e}")

        if not result.text.strip():
            raise HTTPException(422, "Transcription produced no text. Audio may be silent or corrupted.")

        if result.duration_seconds > settings.max_audio_duration_seconds:
            logger.warning(
                "Audio %s is %.0fs (max %ds), will be truncated in analysis.",
                call_id, result.duration_seconds, settings.max_audio_duration_seconds,
            )

        transcript_text = result.text
        transcription_info = TranscriptionInfo(
            source="audio",
            model=f"faster-whisper-{settings.whisper_model}",
            duration_seconds=round(result.duration_seconds, 1),
            confidence=result.confidence,
            text=transcript_text[:2000] + ("..." if len(transcript_text) > 2000 else ""),
        )

    elif is_transcript_file(file.filename):
        # Parse transcript file
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "Invalid text encoding. File must be UTF-8.")

        # Handle JSON transcript format
        if file.filename.lower().endswith(".json"):
            try:
                data = json.loads(text)
                if "segments" in data and isinstance(data["segments"], list):
                    parts = []
                    for seg in data["segments"]:
                        speaker = seg.get("speaker", "")
                        seg_text = seg.get("text", "")
                        if speaker:
                            parts.append(f"{speaker}: {seg_text}")
                        else:
                            parts.append(seg_text)
                    text = "\n".join(parts)
            except json.JSONDecodeError:
                pass  # Treat as plain text

        txt_err = validate_transcript_text(text)
        if txt_err:
            raise HTTPException(400, txt_err)

        transcript_text = text
        transcription_info = TranscriptionInfo(
            source="text",
            text=transcript_text[:2000] + ("..." if len(transcript_text) > 2000 else ""),
        )

    if not transcript_text.strip():
        raise HTTPException(400, "No transcript text could be extracted.")

    assert transcription_info is not None

    # --- AI Analysis ---
    try:
        analysis = await analyze_transcript(transcript_text)
    except AnalysisParseError as e:
        logger.error("Analysis parse error for %s: %s", call_id, e)
        return JSONResponse(
            status_code=422,
            content={
                "detail": str(e),
                "call_id": call_id,
                "raw_llm_response": e.raw_response,
            },
        )
    except Exception as e:
        logger.exception("Analysis failed for %s", call_id)
        raise HTTPException(503, f"Analysis service error: {e}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    input_filename = file.filename if file and file.filename else None
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    model_dir = RESULTS_DIR / date_str / analysis.model_used
    model_dir.mkdir(parents=True, exist_ok=True)
    result_file = model_dir / f"{call_id}-{timestamp_str}.json"

    response = AnalyzeResponse(
        call_id=call_id,
        status="partial" if analysis.flags.requires_manual_review else "success",
        processing_time_ms=elapsed_ms,
        input_file=input_filename,
        result_file=str(result_file),
        transcription=transcription_info,
        analysis=AnalysisWithModel(
            model_used=analysis.model_used,
            **analysis.result.model_dump(),
        ),
        flags=analysis.flags,
    )

    # Save result to file
    result_data = {
        "call_id": call_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processing_time_ms": elapsed_ms,
        "input_file": input_filename,
        "model_used": analysis.model_used,
        "token_usage": {
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "total_tokens": analysis.input_tokens + analysis.output_tokens,
        },
        "result": response.model_dump(),
    }
    result_file.write_text(json.dumps(result_data, indent=2, default=str))
    logger.info("Result saved to %s", result_file)

    return response
