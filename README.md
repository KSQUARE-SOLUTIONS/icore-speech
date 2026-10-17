# Icore Speech Engine

Self-hosted speech service for IcoreSoft projects:

- **Speech → text** (`POST /v1/transcribe`) with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), Arabic first.
- **Text → speech** (`POST /v1/speak`) with [VoiceTut-TTS](https://huggingface.co/mohammedaly22/VoiceTut-TTS) (Egyptian Arabic, voice cloning). Chatterbox and Piper remain as alternative engines.

The same code runs on a Mac and on a server; only `.env` changes. Plan and decisions: *Icore Speech Engine — خطة STT + TTS* (Claude Docs).

## Run locally (macOS, Apple Silicon)

```bash
uv sync --extra voicetut     # Python 3.12 + dependencies + the default TTS engine
cp .env.example .env         # then set ICORE_API_TOKEN
bin/install-command          # once: adds the `icore-speech` command to ~/.local/bin
icore-speech                 # starts the server and opens the page (Ctrl+C stops it)
```

`icore-speech status` shows what is loaded, `icore-speech stop` stops a server started elsewhere,
`icore-speech --no-open` starts without opening the browser.

The page has three tabs: **سماع** (record or drop a file → text), **نطق** (text → speech in any voice)
and **الأصوات** (clone a new voice from a 10–30 s recording, list and delete cloned voices) and
**القاموس** (fix how a word is pronounced, live). Paste the
token once under الإعدادات. Use Chrome or Safari for the microphone.
Models download on first use into `models/` (Whisper `large-v3` ≈ 3.1 GB, VoiceTut ≈ 2.5 GB plus
its audio tokenizer ≈ 0.8 GB).

### Text-to-speech engines

| Engine (`ICORE_TTS_ENGINE`) | Install | Egyptian quality (our listening test) | M1 Pro, per sentence |
| --- | --- | --- | --- |
| `voicetut` (default) | `uv sync --extra voicetut` | Read 5/5 colloquial sentences correctly; 3 sounded natural | ≈ 15–20 s |
| `chatterbox` (+ `ICORE_CHATTERBOX_T3_REPO=NAMAA-Space/NAMAA-Egyptian-TTS`) | `uv sync --extra chatterbox` | Garbled colloquial words even with respelling | ≈ 40–60 s |
| `piper` | base install | Jordanian/MSA voice, robotic | < 1 s |

**VoiceTut needs a GPU.** On the M1 Pro CPU alone (no MPS) one 4 s sentence took 171 s, so a
CPU-only server can run speech-to-text but not this voice. Deployment is on hold (Oct 2026): run
locally until we pick a GPU option (a GPU server, or on-demand serverless GPU for TTS only).

`voicetut` and `chatterbox` need different torch/transformers versions, so only one of the two extras
can be installed at a time. VoiceTut's weights are Apache-2.0, but it was trained on YouTube podcast
audio: review the data rights before selling it to clients.

**Pronunciation fixes.** Write diacritics only on the ambiguous letter (بحبِّك to a woman,
بحبَّك to a man, نعلِّم); they now reach the model. If a word comes out wrong, fix it in the page's **القاموس** tab (word as
typed → how it should sound); it applies immediately and is saved in `data/pronunciations.csv`
(this machine only). Shared fixes for everyone live in `app/text/lexicons/voicetut_overrides.csv`. VoiceTut's own table forced a q
in words like قوي; those are now passed bare, which a listening test showed the model says the
Egyptian way.

**Cloned voices.** VoiceTut and Chatterbox can speak in a recorded person's voice. Build a
reference from that speaker's `/collect` clips (only with their consent):

```bash
uv run python -m evaluation.make_voice_reference karim   # writes voices/karim.wav and voices/karim.txt
```

The API then offers voice `karim` (`GET /v1/voices`, `"voice": "karim"` in `/v1/speak`), next to
VoiceTut's 17 built-in speakers. `ICORE_VOICETUT_DEFAULT_VOICE` picks the default.

## API

All `/v1/*` routes need `Authorization: Bearer <ICORE_API_TOKEN>`. Never ship this token inside a
Flutter or web client: apps call Laravel, Laravel calls this service on the internal network.

| Endpoint | Input | Output |
| --- | --- | --- |
| `POST /v1/transcribe` | multipart: `file`, `language` (`ar` default, `en`, `auto`), `domain` (optional, see `app/text/vocabularies/`), `timestamps` | JSON: `text`, `segments` (when asked), `language`, `audio_seconds`, `processing_ms`, `model_version` |
| `POST /v1/speak` | JSON: `text`, `language` (`ar`/`en`), `voice` (optional), `format` (`mp3`/`wav`) | audio file; `X-Engine`, `X-Voice`, `X-Audio-Seconds`, `X-Processing-Ms` headers |
| `GET /v1/voices` | – | voices of the active TTS engine; `cloned: true` marks cloned ones |
| `POST /v1/voices` | multipart: `file` (5–30 s), `name`, `consent=true`, `reference_text` (optional: transcribed if empty) | the new voice, usable immediately |
| `DELETE /v1/voices/{id}` | – | removes a cloned voice |
| `GET /v1/pronunciations` | – | pronunciation fixes (`source`: `base` from the repo, `local` from the page) |
| `PUT /v1/pronunciations/{word}` | JSON: `spoken` | adds or changes a local fix; applied without restart |
| `DELETE /v1/pronunciations/{word}` | – | removes a local fix |
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

## Recording Egyptian clips

The benchmark (and later an Egyptian voice) needs real recordings with the exact words spoken.
With `ICORE_ENABLE_COLLECTION=true` in `.env`, open http://localhost:8000/collect:

- **جمل جاهزة**: reads the 50 sentences in `evaluation/prompts/egyptian.txt` (numbers, dates, prices,
  places, names, tech terms). Edit the transcript if the speaker said something different.
- **كلام حر**: free speech; Whisper drafts the transcript and the speaker corrects it word by word.

Each clip is saved as mono 24 kHz WAV under `evaluation/audio/<speaker>/` and appended to
`evaluation/manifest.csv`. Recording needs the speaker's consent; audio and manifest stay out of git.
Aim for several speakers, phones and rooms (quiet and noisy) before trusting the numbers.

## Benchmark

Pick a model by measurement, not impression. Record clips (above) or add your own to
`evaluation/manifest.csv` (format: `evaluation/manifest.example.csv`), then:

```bash
uv run python -m evaluation.run_benchmark --manifest evaluation/manifest.csv \
  --models large-v3-turbo small
```

It prints WER (raw and normalised), CER, RTF and latency per model, and writes CSVs to
`evaluation/results/`. `--prompt "<sentence>"` tests a Whisper context sentence.

First results (17 Oct 2026, 50 read prompts, 1 speaker, 3.5 min, M1 Pro CPU int8):

| Model | WER norm | CER norm | RTF |
| --- | --- | --- | --- |
| large-v3 + dialect prompt | **23.3%** | **8.8%** | 2.19 |
| large-v3 | 30.2% | 15.5% | 1.94 |
| large-v3-turbo + dialect prompt | 38.2% | 15.5% | 0.99 |
| large-v3-turbo | 40.5% | 18.4% | 0.83 |
| small | 58.9% | 22.7% | 0.67 |
| MAdel121/whisper-small-egyptian-arabic | 58.9% | 22.7% | 0.37 |

The "Egyptian" small model produced exactly the same text as base `small` on all 50 clips.
One speaker reading prompts is an optimistic, narrow test, and the prompt was chosen on this same
set: re-check with more speakers, free speech and noisy rooms before treating these as final. Normalisation (`app/text/arabic_normalizer.py`) is for scoring only; the API
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
