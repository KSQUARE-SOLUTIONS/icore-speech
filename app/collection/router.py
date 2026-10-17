from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.audio.validation import stored_upload, validate_duration
from app.collection.store import ClipRejected, ClipSource, ClipStore
from app.config import Settings, get_settings
from app.security.auth import require_token


def require_collection_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    if not settings.enable_collection:
        raise HTTPException(404, "Not Found")


router = APIRouter(
    prefix="/v1/collection",
    tags=["collection"],
    dependencies=[Depends(require_collection_enabled), Depends(require_token)],
)


def get_clip_store(request: Request) -> ClipStore:
    return request.app.state.clip_store


@router.get("/prompts")
def list_prompts(store: Annotated[ClipStore, Depends(get_clip_store)], speaker: str = "") -> dict:
    recorded = store.recorded_prompt_ids(speaker) if speaker else set()
    prompts = [{"id": p.id, "text": p.text, "recorded": p.id in recorded} for p in store.prompts()]
    return {"prompts": prompts, "recorded": len(recorded), "total": len(prompts), "stats": store.stats()}


@router.post("/clips")
def save_clip(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[ClipStore, Depends(get_clip_store)],
    file: Annotated[UploadFile, File()],
    speaker: Annotated[str, Form()],
    reference: Annotated[str, Form()],
    consent: Annotated[bool, Form()],
    source: Annotated[ClipSource, Form()] = "prompt",
    prompt_id: Annotated[str | None, Form()] = None,
) -> dict:
    if not consent:
        raise HTTPException(422, "The speaker must agree before a recording is stored.")
    with stored_upload(file.file, file.filename, settings.max_upload_bytes) as path:
        validate_duration(path, settings.max_audio_seconds)
        try:
            clip = store.save(path, speaker, reference, prompt_id, source)
        except ClipRejected as exc:
            raise HTTPException(422, str(exc)) from exc
    return {"clip_id": clip.clip_id, "audio_path": clip.audio_path, "seconds": clip.seconds, "stats": store.stats()}
