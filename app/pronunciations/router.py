from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import get_tts
from app.pronunciations.store import PronunciationRejected, PronunciationStore
from app.security.auth import require_token
from app.tts.base import TtsEngine

router = APIRouter(prefix="/v1/pronunciations", tags=["pronunciations"], dependencies=[Depends(require_token)])


class PronunciationIn(BaseModel):
    spoken: str


def get_pronunciation_store(request: Request) -> PronunciationStore:
    return request.app.state.pronunciation_store


def _apply(tts: TtsEngine) -> None:
    # Engines that support live fixes (VoiceTut) pick them up without a restart.
    reload = getattr(tts, "reload_pronunciations", None)
    if reload:
        reload()


@router.get("")
def list_pronunciations(store: Annotated[PronunciationStore, Depends(get_pronunciation_store)]) -> dict:
    return {"pronunciations": [entry.__dict__ for entry in store.entries()]}


@router.put("/{word}")
def set_pronunciation(
    word: str,
    body: PronunciationIn,
    store: Annotated[PronunciationStore, Depends(get_pronunciation_store)],
    tts: Annotated[TtsEngine, Depends(get_tts)],
) -> dict:
    try:
        entry = store.set(word, body.spoken)
    except PronunciationRejected as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    _apply(tts)
    return entry.__dict__


@router.delete("/{word}", status_code=204)
def delete_pronunciation(
    word: str,
    store: Annotated[PronunciationStore, Depends(get_pronunciation_store)],
    tts: Annotated[TtsEngine, Depends(get_tts)],
) -> None:
    try:
        store.delete(word)
    except PronunciationRejected as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    _apply(tts)
