"""Build a cloning reference for one speaker from their recorded clips.

Chatterbox conditions on the first ~10 s of a reference recording. This picks the speaker's
cleanest clips (lowest background noise, no clipping), joins them with short pauses up to the
target length and writes voices/<speaker>.wav, which the API then offers as voice "<speaker>".

Usage:
    uv run python -m evaluation.make_voice_reference karim
"""

import argparse
import csv

import numpy as np
import soundfile as sf

from app.config import get_settings

PAUSE_SECONDS = 0.3
EDGE_SECONDS = 0.25


def noise_floor(audio: np.ndarray, sample_rate: int) -> float:
    edge = int(EDGE_SECONDS * sample_rate)
    edges = np.concatenate([audio[:edge], audio[-edge:]])
    return float(np.sqrt(np.mean(edges**2)))


def build_reference(speaker: str, target_seconds: float) -> tuple[str, float, int]:
    settings = get_settings()
    manifest = settings.evaluation_dir / "manifest.csv"
    with manifest.open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["speaker"] == speaker]
    if not rows:
        raise SystemExit(f"No clips for speaker '{speaker}' in {manifest}.")

    candidates = []
    for row in rows:
        audio, sample_rate = sf.read(settings.evaluation_dir / row["audio_path"], dtype="float32")
        if np.mean(np.abs(audio) > 0.99) > 0.001:
            continue  # audibly clipped
        candidates.append((noise_floor(audio, sample_rate), audio, sample_rate))
    candidates.sort(key=lambda c: c[0])

    sample_rate = candidates[0][2]
    pause = np.zeros(int(PAUSE_SECONDS * sample_rate), dtype=np.float32)
    pieces, total, used = [], 0.0, 0
    for _, audio, rate in candidates:
        if rate != sample_rate:
            continue
        pieces.extend([audio, pause])
        total += len(audio) / sample_rate + PAUSE_SECONDS
        used += 1
        if total >= target_seconds:
            break

    reference = np.concatenate(pieces)
    reference = reference / max(1e-6, float(np.max(np.abs(reference)))) * 0.9
    target = settings.voices_dir / f"{speaker}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(target, reference, sample_rate, subtype="PCM_16")
    return str(target), round(len(reference) / sample_rate, 1), used


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("speaker")
    parser.add_argument("--seconds", type=float, default=12.0)
    args = parser.parse_args()
    path, seconds, clips = build_reference(args.speaker, args.seconds)
    print(f"{path}: {seconds} s from {clips} clips")


if __name__ == "__main__":
    main()
