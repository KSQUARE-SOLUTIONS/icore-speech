import pytest

from app.config import Settings
from app.tts.base import UnknownVoiceError
from app.tts.chatterbox_engine import ChatterboxEngine


@pytest.fixture
def engine(tmp_path):
    (tmp_path / "karim.wav").write_bytes(b"RIFF")
    (tmp_path / "Bad Name.wav").write_bytes(b"RIFF")
    return ChatterboxEngine(Settings(_env_file=None, voices_dir=tmp_path))


def test_lists_default_and_cloned_voices_per_language(engine):
    pairs = {(v.id, v.language) for v in engine.voices()}
    assert pairs == {("default", "ar"), ("default", "en"), ("karim", "ar"), ("karim", "en")}


@pytest.mark.parametrize("voice", ["missing", "../karim", "Bad Name"])
def test_rejects_unknown_or_unsafe_voices_before_loading_the_model(engine, voice):
    with pytest.raises(UnknownVoiceError):
        engine.synthesize("أهلا", "ar", voice)
    assert not engine.is_loaded


def test_rejects_unsupported_language(engine):
    with pytest.raises(UnknownVoiceError):
        engine.synthesize("hola", "es")
