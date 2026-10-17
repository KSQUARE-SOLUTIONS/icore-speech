import csv
import json
import os
import re
import threading
import time
from pathlib import Path

import numpy as np

from app.config import Settings
from app.tts.base import Speech, UnknownVoiceError, Voice

LANGUAGE_CODES = {"ar": "arz", "en": "en"}  # our codes -> VoiceTut's (arz = Egyptian Arabic)
VOICE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
SKIPPED_FILES = ["optimizer.bin", "random_states_*", "*.pkl", "scheduler.bin"]  # training state, not needed


_DIACRITISED_WORD = re.compile(r"\S*[\u064B-\u0652]\S*")
_PLACEHOLDER_BASE = 0xE000  # Unicode private use area: no normaliser rule touches these


def keep_user_diacritics(normalize):
    """Wrap VoiceTut's normaliser so words the caller diacritised reach the model untouched.

    Undiacritised Egyptian is ambiguous: بحبك is "bahebbak" to a man and "bahebbik" to a woman,
    علم can be "3ilm" or "3allim". VoiceTut strips every diacritic the caller wrote and re-adds
    them only for ~80 words in its own table. Simply not stripping them is not enough: its
    abbreviation rules then see a lone "م" after a diacritic and expand it to "مساءً". So each
    diacritised word is swapped for a private-use placeholder, the rest of the text is normalised
    as usual (numbers, dates, its word table), and the words are put back."""

    def normalize_keeping_diacritics(text: str) -> str:
        words: list[str] = []

        def stash(match: re.Match) -> str:
            words.append(match.group(0))
            return chr(_PLACEHOLDER_BASE + len(words) - 1)

        normalized = normalize(_DIACRITISED_WORD.sub(stash, text))
        for index, word in enumerate(words):
            normalized = normalized.replace(chr(_PLACEHOLDER_BASE + index), word)
        return normalized

    return normalize_keeping_diacritics


QAF = "\u0642"


def pronunciation_overrides(normalizer, overrides_file: Path) -> dict[str, str]:
    """Words VoiceTut should receive as written rather than through its diacritics table.

    A listening test showed the model already says qaf the Egyptian way (قوي -> "awi") when the
    word arrives bare, while VoiceTut's table forced a q (قَوِي). So every table entry containing
    qaf is passed through bare. Then the lines of `overrides_file` (word,spoken) are applied, so
    anyone can fix a mispronounced word without touching code."""
    overrides = {word: word for word in getattr(normalizer, "_diacritics", {}) if QAF in word}
    if overrides_file.is_file():
        lines = [line for line in overrides_file.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        for row in csv.DictReader(lines):
            word, spoken = (row.get("word") or "").strip(), (row.get("spoken") or "").strip()
            if word and spoken:
                overrides[word] = spoken
    return overrides


class VoiceTutEngine:
    """VoiceTut-TTS: OmniVoice fine-tuned on ~380 h of Egyptian podcast speech (Apache-2.0 weights;
    the training audio came from YouTube podcasts, so review data rights before commercial use).

    Voices: the model's 17 built-in speakers, plus every `<voices_dir>/<id>.wav` that has a
    matching `<id>.txt` holding the words spoken in it (zero-shot cloning). It reads Egyptian
    spelling natively and has its own text normaliser, so our Egyptian respelling is skipped."""

    name = "voicetut"
    needs_egyptian_respelling = False

    def __init__(self, settings: Settings):
        self._settings = settings
        self._tts = None
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._tts is not None

    @property
    def _model_dir(self) -> Path:
        return self._settings.models_dir / "voicetut"

    def voices(self) -> list[Voice]:
        built_in = [
            (entry["speaker_name"].lower(), f"Built-in {entry.get('gender', '')} speaker".replace("  ", " "))
            for entry in self._built_in_speakers()
        ]
        cloned = [(voice_id, f"Cloned from {voice_id}.wav") for voice_id in self._cloned_voice_ids()]
        return [
            Voice(id=voice_id, language=language, engine=self.name, description=description)
            for voice_id, description in [*cloned, *built_in]
            for language in LANGUAGE_CODES
        ]

    def load(self) -> None:
        if self._tts is not None:
            return
        with self._load_lock:
            if self._tts is not None:
                return
            # transformers' threaded weight loading segfaults on Apple Silicon (seen with OmniVoice).
            os.environ.setdefault("HF_ENABLE_PARALLEL_LOADING", "false")
            from voicetut_tts import VoiceTutTTS

            self._ensure_model_files()
            device = self._settings.voicetut_device
            if device == "mps":
                # Loading straight onto MPS also segfaults; load on CPU, then move everything except
                # the audio tokenizer, which does not support MPS.
                tts = VoiceTutTTS.from_pretrained(str(self._model_dir), device="cpu")
                tokenizer = tts.model.audio_tokenizer
                tts.model.audio_tokenizer = None
                tts.model.to("mps")
                tts.model.audio_tokenizer = tokenizer
            else:
                tts = VoiceTutTTS.from_pretrained(str(self._model_dir), device=device)
            tts.normalizer.add_lexicon(pronunciation_overrides(tts.normalizer, self._settings.voicetut_overrides_file))
            if self._settings.voicetut_keep_user_diacritics:
                tts.normalizer.normalize = keep_user_diacritics(tts.normalizer.normalize)
            self._tts = tts

    def synthesize(self, text: str, language: str, voice: str | None = None) -> Speech:
        if language not in LANGUAGE_CODES:
            raise UnknownVoiceError(f"VoiceTut supports only {', '.join(LANGUAGE_CODES)}, not '{language}'.")
        voice_id = (voice or self._settings.voicetut_default_voice).lower()
        voice_args = self._voice_arguments(voice_id)

        self.load()
        started = time.perf_counter()
        with self._run_lock:
            audio = self._tts.synthesize(
                text,
                language=LANGUAGE_CODES[language],
                num_step=self._settings.voicetut_num_steps,
                **voice_args,
            )
        return Speech(
            audio=np.asarray(audio, dtype=np.float32).reshape(-1),
            sample_rate=self._tts.sampling_rate,
            voice=voice_id,
            engine=self.name,
            processing_ms=int((time.perf_counter() - started) * 1000),
        )

    def _voice_arguments(self, voice_id: str) -> dict:
        if voice_id in self._cloned_voice_ids():
            reference = self._settings.voices_dir / f"{voice_id}.wav"
            return {"ref_audio": str(reference),
                    "ref_text": reference.with_suffix(".txt").read_text(encoding="utf-8").strip()}
        if voice_id in {entry["speaker_name"].lower() for entry in self._built_in_speakers()}:
            return {"speaker": voice_id}
        raise UnknownVoiceError(f"No VoiceTut voice '{voice_id}'.")

    def _cloned_voice_ids(self) -> list[str]:
        voices_dir = self._settings.voices_dir
        return sorted(
            p.stem for p in voices_dir.glob("*.wav")
            if VOICE_ID.match(p.stem) and p.with_suffix(".txt").is_file()
        )

    def _built_in_speakers(self) -> list[dict]:
        references = self._model_dir / "reference_speakers" / "references.json"
        if not references.is_file():
            return []  # model not downloaded yet; built-in voices appear once it is
        return json.loads(references.read_text(encoding="utf-8"))

    def _ensure_model_files(self) -> None:
        if (self._model_dir / "model.safetensors").is_file():
            return
        from huggingface_hub import snapshot_download

        snapshot_download(self._settings.voicetut_repo, local_dir=self._model_dir, ignore_patterns=SKIPPED_FILES)
