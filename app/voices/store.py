"""Cloned-voice references: voices/<id>.wav (mono, 24 kHz) plus voices/<id>.txt with the words
spoken in it. TTS engines that clone (VoiceTut, Chatterbox) read this folder on every request,
so a new voice is usable immediately, without a restart."""

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from app.audio.decoding import decode_mono
from app.text.arabic_normalizer import clean_whitespace

VOICE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
SAMPLE_RATE = 24000
MIN_SECONDS = 5.0
MAX_SECONDS = 30.0
PEAK = 0.9


class VoiceRejected(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ClonedVoice:
    id: str
    seconds: float
    reference_text: str


class VoiceStore:
    def __init__(self, voices_dir: Path):
        self._dir = voices_dir

    def list(self) -> list[ClonedVoice]:
        voices = []
        for wav in sorted(self._dir.glob("*.wav")):
            text = wav.with_suffix(".txt")
            if VOICE_ID.match(wav.stem) and text.is_file():
                voices.append(ClonedVoice(wav.stem, round(sf.info(wav).duration, 1),
                                          text.read_text(encoding="utf-8").strip()))
        return voices

    def ids(self) -> set[str]:
        return {voice.id for voice in self.list()}

    def create(self, voice_id: str, upload: Path, reference_text: str, reserved_ids: set[str]) -> ClonedVoice:
        if not VOICE_ID.match(voice_id):
            raise VoiceRejected("Name must be 2-32 lowercase English letters, digits, '-' or '_'.")
        if voice_id in reserved_ids:
            raise VoiceRejected(f"'{voice_id}' is a built-in voice name; choose another.", status_code=409)
        if voice_id in self.ids():
            raise VoiceRejected(f"A voice called '{voice_id}' already exists.", status_code=409)
        reference_text = clean_whitespace(reference_text)
        if not reference_text:
            raise VoiceRejected("The words spoken in the recording are required.")

        audio = decode_mono(upload, SAMPLE_RATE)
        seconds = len(audio) / SAMPLE_RATE
        if not MIN_SECONDS <= seconds <= MAX_SECONDS:
            raise VoiceRejected(f"Recording must be {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f} seconds (got {seconds:.1f}).")
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak < 0.01:
            raise VoiceRejected("Recording is silent.")

        self._dir.mkdir(parents=True, exist_ok=True)
        sf.write(self._dir / f"{voice_id}.wav", audio / peak * PEAK, SAMPLE_RATE, subtype="PCM_16")
        (self._dir / f"{voice_id}.txt").write_text(reference_text, encoding="utf-8")
        return ClonedVoice(voice_id, round(seconds, 1), reference_text)

    def delete(self, voice_id: str) -> None:
        if not VOICE_ID.match(voice_id) or voice_id not in self.ids():
            raise VoiceRejected(f"No cloned voice '{voice_id}'.", status_code=404)
        for suffix in (".wav", ".txt"):
            (self._dir / f"{voice_id}{suffix}").unlink(missing_ok=True)
