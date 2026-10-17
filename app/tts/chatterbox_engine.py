import os
import threading
import time

import numpy as np

from app.config import Settings
from app.tts.base import Speech, UnknownVoiceError, Voice

SUPPORTED_LANGUAGES = {"ar": "Arabic", "en": "English"}
DEFAULT_VOICE = "default"


class ChatterboxEngine:
    """Chatterbox Multilingual (MIT). Natural Arabic and English speech; wants a GPU
    (CUDA on a server, MPS on Apple Silicon) for usable speed. Output carries Resemble AI's
    inaudible Perth watermark."""

    name = "chatterbox"

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model = None
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def voices(self) -> list[Voice]:
        return [
            Voice(id=DEFAULT_VOICE, language=code, engine=self.name, description=f"{label} built-in voice")
            for code, label in SUPPORTED_LANGUAGES.items()
        ]

    def load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is None:
                # Let ops that MPS lacks fall back to CPU instead of failing on Apple Silicon.
                os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS

                self._model = ChatterboxMultilingualTTS.from_pretrained(device=self._settings.chatterbox_device)

    def synthesize(self, text: str, language: str, voice: str | None = None) -> Speech:
        if language not in SUPPORTED_LANGUAGES:
            raise UnknownVoiceError(f"Chatterbox is not configured for language '{language}'.")
        if voice not in (None, DEFAULT_VOICE):
            raise UnknownVoiceError(f"No Chatterbox voice '{voice}'.")

        self.load()
        started = time.perf_counter()
        with self._run_lock:
            wav = self._model.generate(text, language_id=language)
        audio = wav.squeeze().detach().cpu().numpy().astype(np.float32)
        return Speech(
            audio=audio,
            sample_rate=self._model.sr,
            voice=DEFAULT_VOICE,
            engine=self.name,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )
