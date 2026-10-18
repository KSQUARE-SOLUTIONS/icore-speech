import pytest

from app.main import app, get_tts
from app.pronunciations.router import get_pronunciation_store
from app.pronunciations.store import PronunciationRejected, PronunciationStore
from tests.conftest import FakeTtsEngine


@pytest.fixture
def store(tmp_path):
    base = tmp_path / "base.csv"
    base.write_text("# shared fixes\nword,spoken\nلية,ليه\n", encoding="utf-8")
    return PronunciationStore(base, tmp_path / "data" / "pronunciations.csv")


def test_local_fixes_override_base_and_persist(store, tmp_path):
    store.set("قهوة", "أهوة")
    store.set("لية", "ليه بس")
    assert {(e.word, e.spoken, e.source) for e in store.entries()} == {
        ("قهوة", "أهوة", "local"), ("لية", "ليه بس", "local"),
    }
    reopened = PronunciationStore(tmp_path / "base.csv", tmp_path / "data" / "pronunciations.csv")
    assert reopened.mapping() == {"قهوة": "أهوة", "لية": "ليه بس"}

    store.delete("لية")
    assert store.mapping()["لية"] == "ليه"  # back to the shared fix


@pytest.mark.parametrize("word", ["two words", "ليه؟", "بحبِّك", "abc", ""])
def test_rejects_words_the_engine_cannot_match(store, word):
    with pytest.raises(PronunciationRejected):
        store.set(word, "x")


def test_base_fixes_cannot_be_deleted_from_the_page(store):
    with pytest.raises(PronunciationRejected) as error:
        store.delete("لية")
    assert error.value.status_code == 409


class ReloadingTts(FakeTtsEngine):
    def __init__(self):
        super().__init__()
        self.reloads = 0

    def reload_pronunciations(self):
        self.reloads += 1


@pytest.fixture
def api(client, store):
    tts = ReloadingTts()
    app.dependency_overrides[get_pronunciation_store] = lambda: store
    app.dependency_overrides[get_tts] = lambda: tts
    return client, tts


def test_api_adds_lists_deletes_and_reloads_the_engine(api, auth):
    client, tts = api
    response = client.put("/v1/pronunciations/قهوة", headers=auth, json={"spoken": "أهوة"})
    assert response.status_code == 200
    assert response.json() == {"word": "قهوة", "spoken": "أهوة", "source": "local"}

    words = {e["word"]: e["source"] for e in client.get("/v1/pronunciations", headers=auth).json()["pronunciations"]}
    assert words == {"قهوة": "local", "لية": "base"}

    assert client.delete("/v1/pronunciations/قهوة", headers=auth).status_code == 204
    assert client.delete("/v1/pronunciations/لية", headers=auth).status_code == 409
    assert tts.reloads == 2


def test_api_rejects_bad_input_and_needs_token(api, auth):
    client, _ = api
    assert client.put("/v1/pronunciations/two words", headers=auth, json={"spoken": "x"}).status_code == 422
    assert client.put("/v1/pronunciations/قهوة", headers=auth, json={"spoken": " "}).status_code == 422
    assert client.get("/v1/pronunciations").status_code == 401


def test_phrases_are_accepted_with_spaces_normalised(store):
    assert store.set("تسلم   ايدك", "تِسْلَم ايدك").word == "تسلم ايدك"


def test_phrase_fixes_apply_only_in_context():
    from app.tts.voicetut_engine import apply_phrases

    normalize = apply_phrases(lambda text: text, lambda: {"تسلم ايدك": "تِسْلَم ايدك"})
    assert normalize("الأكل جميل، تسلم إيدك يا ماما.") == "الأكل جميل، تِسْلَم ايدك يا ماما."
    assert normalize("تسلم على خالتك") == "تسلم على خالتك"
    assert normalize("متسلم ايدك") == "متسلم ايدك"  # never inside a longer word
