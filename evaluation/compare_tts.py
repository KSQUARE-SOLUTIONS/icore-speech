"""Generate the same Egyptian sentences with several Chatterbox checkpoints and voices, so people
can listen side by side.

Usage:
    uv run python -m evaluation.compare_tts --voices karim default \
        --checkpoints base NAMAA-Space/NAMAA-Egyptian-TTS oddadmix/chatterbox-egyptian-v0

Writes evaluation/results/tts-<timestamp>/<checkpoint>__<voice>__<n>.mp3 and a summary CSV.
"""

import argparse
import csv
import gc
from datetime import datetime
from pathlib import Path

from app.audio.encoding import encode
from app.config import get_settings
from app.tts.chatterbox_engine import ChatterboxEngine

SENTENCES = [
    "أهلاً بيك في آي كور سوفت. إزاي نقدر نساعدك النهارده؟",
    "الأوردر بتاعك هيوصل بكرة الصبح، ولو في أي مشكلة كلمنا على طول.",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoints", nargs="+", default=["base"])
    parser.add_argument("--voices", nargs="+", default=["default"])
    parser.add_argument("--texts", nargs="+", default=SENTENCES, help="sentences to render (default: built-in pair)")
    args = parser.parse_args()

    settings = get_settings()
    out_dir = settings.evaluation_dir / "results" / f"tts-{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    for checkpoint in args.checkpoints:
        repo = "" if checkpoint == "base" else checkpoint
        engine = ChatterboxEngine(settings.model_copy(update={"chatterbox_t3_repo": repo}))
        label = checkpoint.split("/")[-1]
        for voice in args.voices:
            for index, sentence in enumerate(args.texts, start=1):
                speech = engine.synthesize(sentence, "ar", voice)
                path = out_dir / f"{label}__{voice}__{index}.mp3"
                path.write_bytes(encode(speech.audio, speech.sample_rate, "mp3"))
                rows.append({"checkpoint": checkpoint, "voice": voice, "sentence": sentence, "file": path.name,
                             "audio_seconds": speech.seconds, "processing_ms": speech.processing_ms})
                print(f"{path.name}: {speech.seconds}s audio in {speech.processing_ms / 1000:.0f}s", flush=True)
        del engine
        gc.collect()

    with (out_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(out_dir)


if __name__ == "__main__":
    main()
