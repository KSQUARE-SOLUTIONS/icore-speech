# Icore Speech Engine

Self-hosted speech service for IcoreSoft projects:

- **Speech → text** (`POST /v1/transcribe`) with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), Arabic first.
- **Text → speech** (`POST /v1/speak`) with [Piper](https://github.com/OHF-Voice/piper1-gpl) (light, local testing) or [Chatterbox Multilingual](https://github.com/resemble-ai/chatterbox) (natural Arabic/English, MIT).

The same code runs on a Mac and on a server; only `.env` changes. Plan and decisions: *Icore Speech Engine — خطة STT + TTS* (Claude Docs).

## Run locally (macOS, Apple Silicon)

```bash
uv sync                      # Python 3.12 + dependencies
cp .env.example .env         # then set ICORE_API_TOKEN
uv run uvicorn app.main:app --port 8000
```

Open http://localhost:8000, paste the token, then record or upload audio, or type text to hear it.
Models download on first use into `models/` (Whisper `large-v3-turbo` ≈ 1.6 GB, each Piper voice ≈ 60 MB).

Chatterbox (≈ 3 GB, uses the Mac GPU through MPS):

```bash
uv sync --extra chatterbox
ICORE_TTS_ENGINE=chatterbox uv run uvicorn app.main:app --port 8000
```

## API

All `/v1/*` routes need `Authorization: Bearer <ICORE_API_TOKEN>`. Never ship this token inside a
Flutter or web client: apps call Laravel, Laravel calls this service on the internal network.

| Endpoint | Input | Output |
| --- | --- | --- |
| `POST /v1/transcribe` | multipart: `file`, `language` (`ar` default, `en`, `auto`), `domain` (optional, see `app/text/vocabularies/`), `timestamps` | JSON: `text`, `segments` (when asked), `language`, `audio_seconds`, `processing_ms`, `model_version` |
| `POST /v1/speak` | JSON: `text`, `language` (`ar`/`en`), `voice` (optional), `format` (`mp3`/`wav`) | audio file; `X-Engine`, `X-Voice`, `X-Audio-Seconds`, `X-Processing-Ms` headers |
| `GET /v1/voices` | – | voices of the active TTS engine |
| `GET /health` | – | loaded models (no token needed) |

```bash
curl -X POST http://localhost:8000/v1/transcribe \
  -H "Authorization: Bearer $ICORE_API_TOKEN" \
  -F file=@clip.m4a -F language=ar -F timestamps=true

curl -X POST http://localhost:8000/v1/speak \
  -H "Authorization: Bearer $ICORE_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"أهلاً بيك","language":"ar","format":"mp3"}' -o hello.mp3
```

Limits (from `.env`): upload 25 MB, audio 600 s, text 1,000 characters. Uploads are stored under a
server-generated name in a temp folder, decoded with FFmpeg to prove they are audio, and deleted
after the request. Logs carry request id, durations and model only, never audio or text.

## Benchmark

Pick a model by measurement, not impression. Put real Egyptian clips under `evaluation/audio/`
(git-ignored), list them with a human-checked reference in `evaluation/manifest.csv`
(format: `evaluation/manifest.example.csv`), then:

```bash
uv run python -m evaluation.run_benchmark --manifest evaluation/manifest.csv \
  --models large-v3-turbo small
```

It prints WER (raw and normalised), CER, RTF and latency per model, and writes CSVs to
`evaluation/results/`. Normalisation (`app/text/arabic_normalizer.py`) is for scoring only; the API
always returns the raw transcript.

## Server

```bash
docker build -t icore-speech .                                  # CPU, Piper
docker build -t icore-speech --build-arg EXTRAS="--extra chatterbox" .
docker run -p 8000:8000 --env-file .env -v icore-models:/app/models icore-speech
```

On an NVIDIA server set `ICORE_STT_DEVICE=cuda`, `ICORE_STT_COMPUTE_TYPE=float16` and
`ICORE_CHATTERBOX_DEVICE=cuda` (needs a CUDA base image). Start on CPU and add a GPU only when the
benchmark shows it is needed.

## Licences to know

- faster-whisper, Whisper weights, Chatterbox, Silero VAD: MIT.
- Piper engine: GPL-3.0 (fine for a server we run; not for code we ship to clients).
- Piper Arabic voice `ar_JO-kareem`: its training data has **no published licence**. Local testing only;
  use Chatterbox in production.
- Chatterbox adds an inaudible Perth watermark to every generated file.

## Tests

```bash
uv run pytest
```
