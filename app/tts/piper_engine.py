import threading
import time
from pathlib import Path

import numpy as np

from app.config import Settings
from app.tts.base import Speech, UnknownVoiceError, Voice

PIPER_VOICES_REPO = "rhasspy/piper-voices"


def _voice_repo_path(voice_id: str) -> str:
    """ar_JO-kareem-medium -> ar/ar_JO/kareem/medium/ar_JO-kareem-medium"""
    locale, name, quality = voice_id.split("-", 2)
    language = locale.split("_", 1)[0]
    return f"{language}/{locale}/{name}/{quality}/{voice_id}"


class PiperEngine:
    """Lightweight CPU text-to-speech. Good for local testing; check each voice's
    training-data licence before using it in production."""

    name = "piper"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._voices: dict[str, object] = {}
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return bool(self._voices)

    def voices(self) -> list[Voice]:
        return [
            Voice(id=voice_id, language=language, engine=self.name)
            for language, voice_id in self._settings.piper_voices.items()
        ]

    def load(self) -> None:
        for voice_id in self._settings.piper_voices.values():
            self._get_voice(voice_id)

    def synthesize(self, text: str, language: str, voice: str | None = None) -> Speech:
        voice_id = voice or self._settings.piper_voices.get(language)
        if voice_id not in self._settings.piper_voices.values():
            raise UnknownVoiceError(f"No Piper voice '{voice_id}' for language '{language}'.")

        piper_voice = self._get_voice(voice_id)
        started = time.perf_counter()
        chunks = list(piper_voice.synthesize(text))
        audio = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
        return Speech(
            audio=audio,
            sample_rate=chunks[0].sample_rate,
            voice=voice_id,
            engine=self.name,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )

    def _get_voice(self, voice_id: str):
        if voice_id in self._voices:
            return self._voices[voice_id]
        with self._lock:
            if voice_id not in self._voices:
                from piper import PiperVoice

                model_path = self._download(voice_id)
                self._voices[voice_id] = PiperVoice.load(str(model_path))
        return self._voices[voice_id]

    def _download(self, voice_id: str) -> Path:
        from huggingface_hub import hf_hub_download

        repo_path = _voice_repo_path(voice_id)
        target = self._settings.models_dir / "piper"
        hf_hub_download(PIPER_VOICES_REPO, f"{repo_path}.onnx.json", local_dir=target)
        return Path(hf_hub_download(PIPER_VOICES_REPO, f"{repo_path}.onnx", local_dir=target))
