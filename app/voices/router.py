from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.audio.validation import stored_upload, validate_duration
from app.config import Settings, get_settings
from app.dependencies import get_stt, get_tts
from app.security.auth import require_token
from app.stt.engine import SttEngine
from app.tts.base import TtsEngine
from app.voices.store import MAX_SECONDS, VoiceRejected, VoiceStore
from app.voices.tones import TONES, split_voice_id, voice_id_for

router = APIRouter(prefix="/v1/voices", tags=["voices"], dependencies=[Depends(require_token)])


def get_voice_store(request: Request) -> VoiceStore:
    return request.app.state.voice_store


@router.get("")
def list_voices(
    tts: Annotated[TtsEngine, Depends(get_tts)],
    store: Annotated[VoiceStore, Depends(get_voice_store)],
) -> dict:
    cloned = store.ids()
    voices = []
    for voice in tts.voices():
        person, tone = split_voice_id(voice.id) if voice.id in cloned else (voice.id, None)
        voices.append(voice.__dict__ | {"cloned": voice.id in cloned, "person": person, "tone": tone})
    return {"engine": tts.name, "tones": TONES, "voices": voices}


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
    tone: Annotated[str, Form()] = "",
    replace: Annotated[bool, Form()] = False,
) -> dict:
    """Add a cloned voice from a 5-30 s recording. Without `reference_text` the words are
    transcribed with Whisper; the transcript is returned so callers can show it. `replace=true`
    re-records an existing cloned voice (a better take of the same tone)."""
    if not consent:
        raise HTTPException(422, "The person whose voice this is must agree to it being cloned.")
    if tone and tone not in TONES:
        raise HTTPException(422, f"Unknown tone '{tone}'. Use one of: {', '.join(TONES)}.")
    person = name.strip().lower()
    if split_voice_id(person)[1]:
        raise HTTPException(422, "Pick the tone from the tone field, not in the name.")
    voice_id = voice_id_for(person, tone or None)
    reserved = {v.id for v in tts.voices()} - store.ids()

    with stored_upload(file.file, file.filename, settings.max_upload_bytes) as path:
        validate_duration(path, int(MAX_SECONDS) + 1)
        text = reference_text.strip()
        if not text:
            prompt = settings.stt_dialect_prompt if language == "ar" else None
            text = stt.transcribe(path, language, prompt).text
        try:
            voice = store.create(voice_id, path, text, reserved, replace)
        except VoiceRejected as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
    person, tone = split_voice_id(voice.id)
    return voice.__dict__ | {"person": person, "tone": tone}


@router.delete("/{voice_id}", status_code=204)
def delete_voice(voice_id: str, store: Annotated[VoiceStore, Depends(get_voice_store)]) -> None:
    try:
        store.delete(voice_id)
    except VoiceRejected as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
