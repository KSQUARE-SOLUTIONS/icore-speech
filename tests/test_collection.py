import csv

import pytest

from app.collection.router import get_clip_store
from app.collection.store import ClipStore
from app.main import app
from tests.conftest import wav_bytes


@pytest.fixture
def evaluation_dir(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "egyptian.txt").write_text("# comment\nصباح الخير\n\nعامل إيه؟\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def collecting(client, settings, evaluation_dir):
    settings.enable_collection = True
    app.dependency_overrides[get_clip_store] = lambda: ClipStore(evaluation_dir, 16000)
    return client


def save(client, auth, **fields):
    data = {"speaker": "karim", "reference": "صباح الخير", "consent": "true", **fields}
    return client.post("/v1/collection/clips", headers=auth, files={"file": ("rec.wav", wav_bytes(), "audio/wav")}, data=data)


def test_collection_is_hidden_when_disabled(client, auth):
    assert client.get("/v1/collection/prompts", headers=auth).status_code == 404
    assert client.get("/collect").status_code == 404


def test_collection_requires_token(collecting):
    assert collecting.get("/v1/collection/prompts").status_code == 401


def test_prompts_skip_comments_and_blank_lines(collecting, auth):
    body = collecting.get("/v1/collection/prompts", headers=auth).json()
    assert [p["text"] for p in body["prompts"]] == ["صباح الخير", "عامل إيه؟"]
    assert body["stats"]["clips"] == 0


def test_saved_clip_is_written_and_listed_in_manifest(collecting, auth, evaluation_dir):
    prompt_id = collecting.get("/v1/collection/prompts", headers=auth).json()["prompts"][0]["id"]
    response = save(collecting, auth, prompt_id=prompt_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (evaluation_dir / body["audio_path"]).exists()
    assert body["stats"] == {"clips": 1, "seconds": 1.0, "speakers": ["karim"]}

    with (evaluation_dir / "manifest.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["reference"] == "صباح الخير"
    assert rows[0]["prompt_id"] == prompt_id

    prompts = collecting.get("/v1/collection/prompts?speaker=karim", headers=auth).json()
    assert prompts["recorded"] == 1
    assert prompts["prompts"][0]["recorded"] is True


def test_rejects_without_consent(collecting, auth):
    assert save(collecting, auth, consent="false").status_code == 422


@pytest.mark.parametrize("speaker", ["../etc", "Karim", "a", "karim/x"])
def test_rejects_unsafe_speaker_names(collecting, auth, speaker):
    assert save(collecting, auth, speaker=speaker).status_code == 422


def test_rejects_unknown_prompt_and_empty_reference(collecting, auth):
    assert save(collecting, auth, prompt_id="nope").status_code == 422
    assert save(collecting, auth, reference="   ").status_code == 422
