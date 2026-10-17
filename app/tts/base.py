from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Voice:
    id: str
    language: str
    engine: str
    description: str = ""


@dataclass(frozen=True)
class Speech:
    audio: np.ndarray  # mono float32 in [-1, 1]
    sample_rate: int
    voice: str
    engine: str
    processing_ms: int

    @property
    def seconds(self) -> float:
        return round(len(self.audio) / self.sample_rate, 2)


class UnknownVoiceError(ValueError):
    pass


class TtsEngine(Protocol):
    """Every text-to-speech backend implements this, so the API never depends on one model."""

    name: str
    # True when the model reads Arabic by MSA rules and benefits from app/text/egyptian_spelling.py.
    needs_egyptian_respelling: bool

    @property
    def is_loaded(self) -> bool: ...

    def load(self) -> None: ...

    def voices(self) -> list[Voice]: ...

    def synthesize(self, text: str, language: str, voice: str | None = None) -> Speech: ...
