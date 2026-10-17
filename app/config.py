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

    stt_model: str = "large-v3-turbo"
    stt_device: Literal["cpu", "cuda", "auto"] = "cpu"
    stt_compute_type: str = "int8"
    stt_cpu_threads: int = 0
    stt_beam_size: int = 5
    stt_vad_filter: bool = True
    stt_default_language: str = "ar"

    tts_engine: Literal["piper", "chatterbox"] = "piper"
    tts_default_language: str = "ar"
    piper_voices: dict[str, str] = {
        "ar": "ar_JO-kareem-medium",
        "en": "en_US-lessac-medium",
    }
    chatterbox_device: Literal["cpu", "mps", "cuda"] = "mps"

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
