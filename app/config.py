from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration. Every value can be overridden from `.env` or the environment
    with the `ICORE_` prefix, so the same code runs on a Mac and on a server."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ICORE_", extra="ignore")

    api_token: str = Field(default="", description="Bearer token required on /v1/* routes.")

    models_dir: Path = PROJECT_ROOT / "models"
    preload_models: bool = False

    # Benchmark on 50 Egyptian clips (Oct 2026): large-v3 + dialect prompt was most accurate
    # (WER 23% vs 38% for large-v3-turbo + prompt) but ~2.2x slower than real time on an M1 CPU.
    stt_model: str = "large-v3"
    stt_device: Literal["cpu", "cuda", "auto"] = "cpu"
    stt_compute_type: str = "int8"
    stt_cpu_threads: int = 0
    stt_beam_size: int = 5
    stt_vad_filter: bool = True
    stt_default_language: str = "ar"
    # Context sentence in Egyptian dialect sent to Whisper on every Arabic request. Steers it toward
    # colloquial spelling; cut normalised WER 30% -> 23% on large-v3. Empty string disables it.
    stt_dialect_prompt: str = "إزيك، عامل إيه النهارده؟ أنا كنت عايز أسأل على حاجة لو سمحت."

    # Listening test (Oct 2026): VoiceTut read colloquial Egyptian correctly where Chatterbox/NAMAA garbled it.
    tts_engine: Literal["voicetut", "chatterbox", "piper"] = "voicetut"
    tts_default_language: str = "ar"
    # Respell Arabic text before TTS so MSA-trained models say it the Egyptian way
    # (app/text/egyptian_spelling.py). Requests can override both per call.
    tts_egyptian_spelling: bool = True
    tts_qaf_as_hamza: bool = True
    piper_voices: dict[str, str] = {
        "ar": "ar_JO-kareem-medium",
        "en": "en_US-lessac-medium",
    }
    chatterbox_device: Literal["cpu", "mps", "cuda"] = "mps"
    # Hugging Face repo whose t3_mtl23ls_v2.safetensors replaces the base text-to-speech weights,
    # e.g. an Egyptian fine-tune such as "NAMAA-Space/NAMAA-Egyptian-TTS". Empty = base Chatterbox.
    # Listening test (Oct 2026): NAMAA + Egyptian respelling sounded most Egyptian of base/NAMAA/oddadmix.
    chatterbox_t3_repo: str = "NAMAA-Space/NAMAA-Egyptian-TTS"
    voicetut_repo: str = "mohammedaly22/VoiceTut-TTS"
    voicetut_device: Literal["cpu", "mps", "cuda"] = "mps"
    voicetut_num_steps: int = 32
    # Pass diacritics written in the text (بحبكِ, نعلِّم) through to the model instead of stripping them.
    voicetut_keep_user_diacritics: bool = True
    # word,spoken lines that fix how VoiceTut says specific words (see the file's header).
    voicetut_overrides_file: Path = PROJECT_ROOT / "app" / "text" / "lexicons" / "voicetut_overrides.csv"
    # A built-in speaker (e.g. "mohamed", "asmaa") or a cloned voice id from voices_dir.
    voicetut_default_voice: str = "mohamed"
    # Reference recordings for cloned voices: <voices_dir>/<voice_id>.wav (about 10 s each).
    voices_dir: Path = PROJECT_ROOT / "voices"

    # Recording page that builds the Egyptian test set (and later a voice dataset).
    # Writes audio to disk, so keep it off on shared servers.
    enable_collection: bool = False
    evaluation_dir: Path = PROJECT_ROOT / "evaluation"
    collection_sample_rate: int = 24000

    max_upload_mb: int = 25
    max_audio_seconds: int = 600
    max_text_chars: int = 1000

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
