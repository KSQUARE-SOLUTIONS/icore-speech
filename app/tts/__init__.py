from app.config import Settings
from app.tts.base import TtsEngine


def build_tts_engine(settings: Settings) -> TtsEngine:
    if settings.tts_engine == "chatterbox":
        from app.tts.chatterbox_engine import ChatterboxEngine

        return ChatterboxEngine(settings)

    from app.tts.piper_engine import PiperEngine

    return PiperEngine(settings)
