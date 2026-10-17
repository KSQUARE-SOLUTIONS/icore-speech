import os
import re
import threading
import time
from pathlib import Path

import numpy as np

from app.config import Settings
from app.tts.base import Speech, UnknownVoiceError, Voice

SUPPORTED_LANGUAGES = {"ar": "Arabic", "en": "English"}
DEFAULT_VOICE = "default"
VOICE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


class ChatterboxEngine:
    """Chatterbox Multilingual (MIT). Natural Arabic and English speech; wants a GPU
    (CUDA on a server, MPS on Apple Silicon) for usable speed. Output carries Resemble AI's
    inaudible Perth watermark.

    Besides its built-in voice it can clone any voice from a ~10 s reference recording:
    every `<voices_dir>/<id>.wav` becomes a voice called `<id>`. Only add recordings of people
    who agreed to have their voice cloned."""

    name = "chatterbox"
    needs_egyptian_respelling = True

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model = None
        self._conditionals: dict[str, object] = {}
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def voices(self) -> list[Voice]:
        cloned = sorted(p.stem for p in self._voices_dir.glob("*.wav") if VOICE_ID.match(p.stem))
        return [
            Voice(id=voice_id, language=code, engine=self.name,
                  description=f"{label} built-in voice" if voice_id == DEFAULT_VOICE else f"Cloned from {voice_id}.wav")
            for voice_id in [DEFAULT_VOICE, *cloned]
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

                device = self._settings.chatterbox_device
                model = ChatterboxMultilingualTTS.from_pretrained(device=device)
                if self._settings.chatterbox_t3_repo:
                    self._load_t3_weights(model, self._settings.chatterbox_t3_repo, device)
                self._conditionals[DEFAULT_VOICE] = model.conds
                self._model = model

    def synthesize(self, text: str, language: str, voice: str | None = None) -> Speech:
        if language not in SUPPORTED_LANGUAGES:
            raise UnknownVoiceError(f"Chatterbox is not configured for language '{language}'.")
        voice_id = voice or DEFAULT_VOICE
        reference = self._reference_path(voice_id)

        self.load()
        started = time.perf_counter()
        with self._run_lock:
            # The model keeps one active voice (its "conditionals"); swap in the requested one,
            # computing it from the reference recording only the first time.
            if voice_id not in self._conditionals:
                self._model.prepare_conditionals(str(reference))
                self._conditionals[voice_id] = self._model.conds
            self._model.conds = self._conditionals[voice_id]
            wav = self._model.generate(text, language_id=language)
        audio = wav.squeeze().detach().cpu().numpy().astype(np.float32)
        return Speech(
            audio=audio,
            sample_rate=self._model.sr,
            voice=voice_id,
            engine=self.name,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _load_t3_weights(model, repo_id: str, device: str) -> None:
        """Swap in fine-tuned text-to-speech-token weights (the part that decides pronunciation);
        the vocoder and speaker encoder stay the base model's."""
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file

        path = hf_hub_download(repo_id, "t3_mtl23ls_v2.safetensors")
        model.t3.load_state_dict(load_file(path, device=device))
        model.t3.to(device).eval()

    @property
    def _voices_dir(self) -> Path:
        return self._settings.voices_dir

    def _reference_path(self, voice_id: str) -> Path | None:
        if voice_id == DEFAULT_VOICE:
            return None
        path = self._voices_dir / f"{voice_id}.wav"
        if not VOICE_ID.match(voice_id) or not path.is_file():
            raise UnknownVoiceError(f"No Chatterbox voice '{voice_id}'.")
        return path
