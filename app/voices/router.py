from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.audio.validation import stored_upload, validate_duration
from app.config import Settings, get_settings
from app.dependencies import get_stt, get_tts
from app.security.auth import require_token
from app.stt.engine import SttEngine
from app.tts.base import TtsEngine
from app.voices.store import MAX_SECONDS, VoiceRejected, VoiceStore

router = APIRouter(prefix="/v1/voices", tags=["voices"], dependencies=[Depends(require_token)])


def get_voice_store(request: Request) -> VoiceStore:
    return request.app.state.voice_store


@router.get("")
def list_voices(
    tts: Annotated[TtsEngine, Depends(get_tts)],
    store: Annotated[VoiceStore, Depends(get_voice_store)],
) -> dict:
    cloned = store.ids()
    return {
        "engine": tts.name,
        "voices": [v.__dict__ | {"cloned": v.id in cloned} for v in tts.voices()],
    }


@router.post("", status_code=201)
def clone_voice(
    settings: Annotated[Settings, Depends(get_settings)],
    stt: Annotated[SttEngine, Depends(get_stt)],
    tts: Annotated[TtsEngine, Depends(get_tts)],
    store: Annotated[VoiceStore, Depends(get_voice_store)],
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()],
    consent: Annotated[bool, Form()],
    reference_text: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "ar",
) -> dict:
    """Add a cloned voice from a 5-30 s recording. Without `reference_text` the words are
    transcribed with Whisper; the transcript is returned so callers can show it."""
    if not consent:
        raise HTTPException(422, "The person whose voice this is must agree to it being cloned.")
    voice_id = name.strip().lower()
    reserved = {v.id for v in tts.voices()} - store.ids()

    with stored_upload(file.file, file.filename, settings.max_upload_bytes) as path:
        validate_duration(path, int(MAX_SECONDS) + 1)
        text = reference_text.strip()
        if not text:
            prompt = settings.stt_dialect_prompt if language == "ar" else None
            text = stt.transcribe(path, language, prompt).text
        try:
            voice = store.create(voice_id, path, text, reserved)
        except VoiceRejected as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
    return voice.__dict__


@router.delete("/{voice_id}", status_code=204)
def delete_voice(voice_id: str, store: Annotated[VoiceStore, Depends(get_voice_store)]) -> None:
    try:
        store.delete(voice_id)
    except VoiceRejected as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
