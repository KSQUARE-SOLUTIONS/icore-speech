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


def test_diacritised_words_reach_the_model_untouched():
    normalization = pytest.importorskip("voicetut_tts.normalization")
    from app.tts.voicetut_engine import keep_user_diacritics

    normalize = keep_user_diacritics(normalization.ArabicNormalizer().normalize)
    # Shadda before م must not be read as the "م" (p.m.) abbreviation.
    assert normalize("لازم نعلّم الولاد يِحْتِرْمُوا").endswith("نعلّم الولاد يِحْتِرْمُوا")
    assert "بحبِّك" in normalize("بحبِّك قوي")
    # Undiacritised words still get VoiceTut's own handling.
    assert "مساءً" in normalize("الساعة 5 م")
    assert normalize("ازيك") == "إِزَّيَّك"


class FakeNormalizer:
    _diacritics = {"قوي": "قَوِي", "بقى": "بَقَى", "ازيك": "إِزَّيَّك"}


def test_overrides_pass_qaf_words_bare_and_read_the_file(tmp_path):
    from app.tts.voicetut_engine import pronunciation_overrides

    overrides_file = tmp_path / "overrides.csv"
    overrides_file.write_text("# comment\nword,spoken\nقهوة,أهوة\n\n", encoding="utf-8")
    assert pronunciation_overrides(FakeNormalizer(), overrides_file) == {"قوي": "قوي", "بقى": "بقى", "قهوة": "أهوة"}
    assert pronunciation_overrides(FakeNormalizer(), tmp_path / "missing.csv") == {"قوي": "قوي", "بقى": "بقى"}


def test_real_normaliser_keeps_qaf_words_bare():
    normalization = pytest.importorskip("voicetut_tts.normalization")
    from app.config import Settings
    from app.tts.voicetut_engine import pronunciation_overrides

    normalizer = normalization.ArabicNormalizer()
    normalizer.add_lexicon(pronunciation_overrides(normalizer, Settings(_env_file=None).voicetut_overrides_file))
    assert "قوي" in normalizer.normalize("حلو قوي").split()
    assert normalizer.normalize("ازيك") == "إِزَّيَّك"  # other table words keep VoiceTut's form
