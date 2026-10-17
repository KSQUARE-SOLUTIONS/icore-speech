import pytest

from app.main import app
from app.tts.base import Voice
from app.voices.router import get_voice_store
from app.voices.store import VoiceStore
from tests.conftest import FakeTtsEngine, wav_bytes


def tone_wav(seconds: float) -> bytes:
    """A real (non-silent) WAV so the store's silence check passes."""
    import io

    import numpy as np
    import soundfile as sf

    rate = 16000
    t = np.arange(int(seconds * rate)) / rate
    buffer = io.BytesIO()
    sf.write(buffer, 0.3 * np.sin(2 * np.pi * 220 * t), rate, format="WAV")
    return buffer.getvalue()


class CloningTtsEngine(FakeTtsEngine):
    """Lists one built-in voice plus whatever the store holds, like VoiceTut."""

    def __init__(self, store: VoiceStore):
        super().__init__()
        self.store = store

    def voices(self):
        ids = ["mohamed", *self.store.ids()]
        return [Voice(id=i, language="ar", engine=self.name) for i in ids]


@pytest.fixture
def store(tmp_path):
    return VoiceStore(tmp_path / "voices")


@pytest.fixture
def cloning(client, store, tts):
    from app.main import get_tts

    app.dependency_overrides[get_voice_store] = lambda: store
    app.dependency_overrides[get_tts] = lambda: CloningTtsEngine(store)
    return client


def clone(client, auth, name="sara", seconds=8.0, **fields):
    data = {"name": name, "consent": "true", **fields}
    return client.post("/v1/voices", headers=auth, files={"file": ("ref.wav", tone_wav(seconds), "audio/wav")}, data=data)


def test_clone_lists_and_deletes_a_voice(cloning, auth, store):
    response = clone(cloning, auth, reference_text="أهلا أنا سارة")
    assert response.status_code == 201, response.text
    assert response.json() == {"id": "sara", "seconds": 8.0, "reference_text": "أهلا أنا سارة"}

    voices = cloning.get("/v1/voices", headers=auth).json()["voices"]
    assert {(v["id"], v["cloned"]) for v in voices} == {("mohamed", False), ("sara", True)}

    assert cloning.delete("/v1/voices/sara", headers=auth).status_code == 204
    assert store.ids() == set()
    assert cloning.delete("/v1/voices/sara", headers=auth).status_code == 404


def test_transcribes_reference_when_text_is_missing(cloning, auth, stt):
    response = clone(cloning, auth)
    assert response.status_code == 201
    assert response.json()["reference_text"] == "أهلا بيك"  # FakeSttEngine's transcript
    assert stt.calls[0]["language"] == "ar"


def test_name_is_lowercased(cloning, auth):
    assert clone(cloning, auth, name="Sara", reference_text="أهلا").json()["id"] == "sara"


@pytest.mark.parametrize(
    ("fields", "status"),
    [
        ({"consent": "false"}, 422),
        ({"name": "../etc"}, 422),
        ({"name": "mohamed"}, 409),
        ({"seconds": 3.0}, 422),
    ],
)
def test_rejects_bad_clones(cloning, auth, fields, status):
    seconds = fields.pop("seconds", 8.0)
    assert clone(cloning, auth, seconds=seconds, reference_text="أهلا", **fields).status_code == status


def test_rejects_duplicate_and_silent_recordings(cloning, auth):
    assert clone(cloning, auth, reference_text="أهلا").status_code == 201
    assert clone(cloning, auth, reference_text="أهلا").status_code == 409
    silent = cloning.post(
        "/v1/voices", headers=auth,
        files={"file": ("ref.wav", wav_bytes(seconds=8), "audio/wav")},
        data={"name": "quiet", "consent": "true", "reference_text": "أهلا"},
    )
    assert silent.status_code == 422


def test_voices_routes_need_token(cloning):
    assert cloning.get("/v1/voices").status_code == 401
    assert cloning.delete("/v1/voices/sara").status_code == 401
