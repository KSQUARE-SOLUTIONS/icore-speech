from fastapi import Request

from app.stt.engine import SttEngine
from app.tts.base import TtsEngine


def get_stt(request: Request) -> SttEngine:
    return request.app.state.stt


def get_tts(request: Request) -> TtsEngine:
    return request.app.state.tts
