import json

import pytest

from app.config import Settings
from app.tts.base import UnknownVoiceError
from app.tts.voicetut_engine import VoiceTutEngine


@pytest.fixture
def engine(tmp_path):
    references = tmp_path / "models" / "voicetut" / "reference_speakers"
    references.mkdir(parents=True)
    (references / "references.json").write_text(
        json.dumps([{"speaker_id": "spk_01", "speaker_name": "Mohamed", "audio_path": "x.wav",
                     "reference_text": "أهلا", "gender": "male"}]),
        encoding="utf-8",
    )
    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "karim.wav").write_bytes(b"RIFF")
    (voices / "karim.txt").write_text("صباح الخير", encoding="utf-8")
    (voices / "notext.wav").write_bytes(b"RIFF")  # no transcript, so not a usable clone
    return VoiceTutEngine(Settings(_env_file=None, models_dir=tmp_path / "models", voices_dir=voices))


def test_lists_cloned_and_built_in_voices_per_language(engine):
    pairs = {(v.id, v.language) for v in engine.voices()}
    assert pairs == {("karim", "ar"), ("karim", "en"), ("mohamed", "ar"), ("mohamed", "en")}


def test_maps_voices_to_reference_or_speaker(engine):
    assert engine._voice_arguments("karim")["ref_text"] == "صباح الخير"
    assert engine._voice_arguments("mohamed") == {"speaker": "mohamed"}


@pytest.mark.parametrize("voice", ["notext", "../karim", "nobody"])
def test_rejects_unknown_voices_before_loading_the_model(engine, voice):
    with pytest.raises(UnknownVoiceError):
        engine.synthesize("أهلا", "ar", voice)
    assert not engine.is_loaded


def test_rejects_unsupported_language(engine):
    with pytest.raises(UnknownVoiceError):
        engine.synthesize("hola", "es")


def test_skips_egyptian_respelling():
    assert VoiceTutEngine.needs_egyptian_respelling is False
