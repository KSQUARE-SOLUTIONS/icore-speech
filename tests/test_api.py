from tests.conftest import wav_bytes


def test_health_needs_no_token(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["stt"]["model"] == "fake-whisper"


def test_v1_routes_reject_missing_or_wrong_token(client):
    assert client.get("/v1/voices").status_code == 401
    assert client.get("/v1/voices", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_v1_routes_refuse_when_no_token_configured(client, settings):
    settings.api_token = ""
    assert client.get("/v1/voices", headers={"Authorization": "Bearer "}).status_code == 503


def test_transcribe_returns_text(client, auth, stt):
    response = client.post(
        "/v1/transcribe",
        headers=auth,
        files={"file": ("clip.wav", wav_bytes(), "audio/wav")},
        data={"language": "ar"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "أهلا بيك"
    assert body["request_id"].startswith("req_")
    assert "segments" not in body
    assert stt.calls == [{"language": "ar", "initial_prompt": None}]


def test_transcribe_returns_segments_when_asked(client, auth):
    response = client.post(
        "/v1/transcribe",
        headers=auth,
        files={"file": ("clip.wav", wav_bytes(), "audio/wav")},
        data={"timestamps": "true"},
    )
    assert response.json()["segments"] == [{"start": 0.0, "end": 1.0, "text": "أهلا بيك"}]


def test_transcribe_auto_language_and_domain_prompt(client, auth, stt):
    client.post(
        "/v1/transcribe",
        headers=auth,
        files={"file": ("clip.wav", wav_bytes(), "audio/wav")},
        data={"language": "auto", "domain": "general"},
    )
    assert stt.calls[0]["language"] is None
    assert "IcoreSoft" in stt.calls[0]["initial_prompt"]


def test_transcribe_rejects_unknown_domain(client, auth):
    response = client.post(
        "/v1/transcribe",
        headers=auth,
        files={"file": ("clip.wav", wav_bytes(), "audio/wav")},
        data={"domain": "../../etc"},
    )
    assert response.status_code == 422


def test_transcribe_rejects_bad_extension(client, auth):
    response = client.post("/v1/transcribe", headers=auth, files={"file": ("run.sh", b"echo hi", "audio/wav")})
    assert response.status_code == 415


def test_transcribe_rejects_fake_audio_with_audio_extension(client, auth):
    response = client.post("/v1/transcribe", headers=auth, files={"file": ("clip.wav", b"not audio" * 100, "audio/wav")})
    assert response.status_code == 415


def test_transcribe_rejects_file_over_size_limit(client, auth):
    too_big = b"\x00" * (1024 * 1024 + 1)
    response = client.post("/v1/transcribe", headers=auth, files={"file": ("clip.wav", too_big, "audio/wav")})
    assert response.status_code == 413


def test_transcribe_rejects_audio_over_duration_limit(client, auth):
    response = client.post("/v1/transcribe", headers=auth, files={"file": ("long.wav", wav_bytes(seconds=6), "audio/wav")})
    assert response.status_code == 413


def test_speak_returns_audio(client, auth):
    response = client.post("/v1/speak", headers=auth, json={"text": "أهلا", "format": "wav"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"
    assert response.headers["X-Engine"] == "fake-tts"


def test_speak_mp3(client, auth):
    response = client.post("/v1/speak", headers=auth, json={"text": "أهلا", "format": "mp3"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 100


def test_speak_rejects_long_text(client, auth):
    response = client.post("/v1/speak", headers=auth, json={"text": "ا" * 51})
    assert response.status_code == 413


def test_speak_rejects_blank_text_and_unknown_voice(client, auth):
    assert client.post("/v1/speak", headers=auth, json={"text": "   "}).status_code == 422
    assert client.post("/v1/speak", headers=auth, json={"text": "أهلا", "voice": "nope"}).status_code == 422
