import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcription:
    text: str
    language: str
    language_probability: float
    audio_seconds: float
    processing_ms: int
    model: str
    segments: list[Segment] = field(default_factory=list)


class SttEngine:
    """faster-whisper wrapper. The model is loaded once and reused; calls are serialised
    because one CTranslate2 model already uses every CPU thread it is given."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model = None
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._settings.stt_model

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._settings.stt_model,
                device=self._settings.stt_device,
                compute_type=self._settings.stt_compute_type,
                cpu_threads=self._settings.stt_cpu_threads,
                download_root=str(self._settings.models_dir / "whisper"),
            )

    def transcribe(
        self,
        audio_path: Path,
        language: str | None,
        initial_prompt: str | None = None,
    ) -> Transcription:
        self.load()
        started = time.perf_counter()
        with self._run_lock:
            segments_iter, info = self._model.transcribe(
                str(audio_path),
                language=language,
                task="transcribe",
                beam_size=self._settings.stt_beam_size,
                vad_filter=self._settings.stt_vad_filter,
                initial_prompt=initial_prompt,
            )
            # The iterator is lazy: decoding happens here, so keep it inside the lock.
            segments = [Segment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments_iter]

        return Transcription(
            text=" ".join(s.text for s in segments if s.text).strip(),
            language=info.language,
            language_probability=round(info.language_probability, 3),
            audio_seconds=round(info.duration, 2),
            processing_ms=int((time.perf_counter() - started) * 1000),
            model=self.model_name,
            segments=segments,
        )
