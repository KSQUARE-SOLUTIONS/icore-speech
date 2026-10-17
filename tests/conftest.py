import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, get_stt, get_tts
from app.stt.engine import Segment, Transcription
from app.tts.base import Speech, UnknownVoiceError, Voice

TOKEN = "test-token"


class FakeSttEngine:
    model_name = "fake-whisper"
    is_loaded = True

    def __init__(self):
        self.calls = []

    def load(self):
        pass

    def transcribe(self, audio_path, language, initial_prompt=None):
        self.calls.append({"language": language, "initial_prompt": initial_prompt})
        return Transcription(
            text="أهلا بيك",
            language=language or "ar",
            language_probability=0.99,
            audio_seconds=1.0,
            processing_ms=5,
            model=self.model_name,
            segments=[Segment(0.0, 1.0, "أهلا بيك")],
        )


class FakeTtsEngine:
    name = "fake-tts"
    is_loaded = True

    def load(self):
        pass

    def voices(self):
        return [Voice(id="fake-ar", language="ar", engine=self.name)]

    def synthesize(self, text, language, voice=None):
        if voice not in (None, "fake-ar"):
            raise UnknownVoiceError(f"No voice '{voice}'.")
        return Speech(
            audio=np.zeros(16000, dtype=np.float32),
            sample_rate=16000,
            voice="fake-ar",
            engine=self.name,
            processing_ms=3,
        )


def wav_bytes(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buffer.getvalue()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, api_token=TOKEN, max_upload_mb=1, max_audio_seconds=5, max_text_chars=50)


@pytest.fixture
def stt() -> FakeSttEngine:
    return FakeSttEngine()


@pytest.fixture
def client(settings, stt):
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_stt] = lambda: stt
    app.dependency_overrides[get_tts] = lambda: FakeTtsEngine()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"}
