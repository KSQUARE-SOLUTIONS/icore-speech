import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.audio.encoding import MEDIA_TYPES, encode
from app.audio.validation import AudioRejected, stored_upload, validate_duration
from app.collection.router import require_collection_enabled
from app.collection.router import router as collection_router
from app.collection.store import ClipStore
from app.config import PROJECT_ROOT, Settings, get_settings
from app.dependencies import get_stt, get_tts
from app.pronunciations.router import router as pronunciations_router
from app.pronunciations.store import PronunciationStore
from app.security.auth import require_token
from app.stt.engine import SttEngine
from app.text.addressee import Addressee, mark_addressee
from app.text.egyptian_spelling import egyptian_spelling
from app.text.vocabulary import UnknownDomainError, prompt_for
from app.tts import build_tts_engine
from app.tts.base import TtsEngine, UnknownVoiceError
from app.voices.router import get_voice_store
from app.voices.router import router as voices_router
from app.voices.tones import TONES, split_voice_id, voice_id_for
from app.voices.store import VoiceStore

logger = logging.getLogger("icore_speech")
LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}$")
STATIC_DIR = PROJECT_ROOT / "app" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Honour a test override so tests never read the developer's .env (e.g. preload_models=true).
    settings = app.dependency_overrides.get(get_settings, get_settings)()
    app.state.stt = SttEngine(settings)
    app.state.tts = build_tts_engine(settings)
    app.state.clip_store = ClipStore(settings.evaluation_dir, settings.collection_sample_rate)
    app.state.voice_store = VoiceStore(settings.voices_dir)
    app.state.pronunciation_store = PronunciationStore(settings.voicetut_overrides_file, settings.pronunciations_file)
    if settings.preload_models:
        app.state.stt.load()
        app.state.tts.load()
    yield


app = FastAPI(title="Icore Speech Engine", version="0.1.0", lifespan=lifespan)
app.include_router(collection_router)
app.include_router(voices_router)
app.include_router(pronunciations_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(AudioRejected)
async def audio_rejected_handler(_: Request, exc: AudioRejected) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


class SegmentOut(BaseModel):
    start: float
    end: float
    text: str


class TranscribeResponse(BaseModel):
    request_id: str
    status: Literal["completed"] = "completed"
    language: str
    language_probability: float
    text: str
    segments: list[SegmentOut] | None = None
    audio_seconds: float
    processing_ms: int
    model_version: str


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str = "ar"
    voice: str | None = None
    format: Literal["wav", "mp3"] = "mp3"
    # Emotion: picks the person's recording in that tone (voice "karim" + tone "excited" -> karim-excited).
    tone: str | None = None
    # Who is being spoken to; marks second-person endings (ايدك -> ايدِك for a woman). Arabic only.
    addressee: Addressee = "auto"
    egyptian_spelling: bool | None = None  # None = server default
    qaf_as_hamza: bool | None = None


@app.get("/", include_in_schema=False)
def test_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/collect", include_in_schema=False, dependencies=[Depends(require_collection_enabled)])
def collection_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "collect.html")


@app.get("/health")
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    stt: Annotated[SttEngine, Depends(get_stt)],
    tts: Annotated[TtsEngine, Depends(get_tts)],
) -> dict:
    return {
        "status": "ok",
        "stt": {"model": stt.model_name, "device": settings.stt_device, "loaded": stt.is_loaded},
        "tts": {"engine": tts.name, "loaded": tts.is_loaded},
    }


@app.post("/v1/transcribe", dependencies=[Depends(require_token)], response_model_exclude_none=True)
def transcribe(
    settings: Annotated[Settings, Depends(get_settings)],
    stt: Annotated[SttEngine, Depends(get_stt)],
    file: Annotated[UploadFile, File()],
    language: Annotated[str, Form()] = "ar",
    domain: Annotated[str | None, Form()] = None,
    timestamps: Annotated[bool, Form()] = False,
) -> TranscribeResponse:
    request_id = f"req_{uuid.uuid4().hex[:16]}"
    if language != "auto" and not LANGUAGE_CODE.match(language):
        raise HTTPException(422, "language must be an ISO code such as 'ar' or 'en', or 'auto'.")
    try:
        domain_terms = prompt_for(domain) if domain else None
    except UnknownDomainError as exc:
        raise HTTPException(422, str(exc)) from exc
    dialect = settings.stt_dialect_prompt if language == "ar" else ""
    prompt = " ".join(part for part in (dialect, domain_terms) if part) or None

    with stored_upload(file.file, file.filename, settings.max_upload_bytes) as path:
        validate_duration(path, settings.max_audio_seconds)
        result = stt.transcribe(path, None if language == "auto" else language, prompt)

    logger.info(
        "transcribe request_id=%s audio_s=%.1f processing_ms=%d model=%s",
        request_id, result.audio_seconds, result.processing_ms, result.model,
    )
    return TranscribeResponse(
        request_id=request_id,
        language=result.language,
        language_probability=result.language_probability,
        text=result.text,
        segments=[SegmentOut(**s.__dict__) for s in result.segments] if timestamps else None,
        audio_seconds=result.audio_seconds,
        processing_ms=result.processing_ms,
        model_version=result.model,
    )


@app.post("/v1/speak", dependencies=[Depends(require_token)])
def speak(
    body: SpeakRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    tts: Annotated[TtsEngine, Depends(get_tts)],
    voice_store: Annotated[VoiceStore, Depends(get_voice_store)],
) -> Response:
    request_id = f"req_{uuid.uuid4().hex[:16]}"
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "text is empty.")
    if len(text) > settings.max_text_chars:
        raise HTTPException(413, f"text is longer than {settings.max_text_chars} characters.")
    spoken_text = mark_addressee(text, body.addressee) if body.language == "ar" else text
    respell = settings.tts_egyptian_spelling if body.egyptian_spelling is None else body.egyptian_spelling
    if body.language == "ar" and respell and tts.needs_egyptian_respelling:
        qaf = settings.tts_qaf_as_hamza if body.qaf_as_hamza is None else body.qaf_as_hamza
        spoken_text = egyptian_spelling(spoken_text, qaf_as_hamza=qaf)
    voice = body.voice
    if body.tone:
        if body.tone not in TONES:
            raise HTTPException(422, f"Unknown tone '{body.tone}'. Use one of: {', '.join(TONES)}.")
        if not body.voice:
            raise HTTPException(422, "A tone needs a voice (e.g. voice=karim, tone=excited).")
        voice = voice_id_for(split_voice_id(body.voice)[0], body.tone)
        if voice not in voice_store.ids():
            raise HTTPException(422, f"No '{TONES[body.tone]}' recording for '{body.voice}' yet: record one in the voices tab.")
    try:
        speech = tts.synthesize(spoken_text, body.language, voice)
    except UnknownVoiceError as exc:
        raise HTTPException(422, str(exc)) from exc

    logger.info(
        "speak request_id=%s chars=%d audio_s=%.1f processing_ms=%d engine=%s",
        request_id, len(text), speech.seconds, speech.processing_ms, speech.engine,
    )
    return Response(
        content=encode(speech.audio, speech.sample_rate, body.format),
        media_type=MEDIA_TYPES[body.format],
        headers={
            "X-Request-Id": request_id,
            "X-Engine": speech.engine,
            "X-Voice": speech.voice,
            "X-Audio-Seconds": str(speech.seconds),
            "X-Processing-Ms": str(speech.processing_ms),
        },
    )
