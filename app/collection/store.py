"""Stores recorded clips and their reference transcripts for the benchmark (and, later, a voice
dataset). Audio lands in `evaluation/audio/<speaker>/` and one row per clip is appended to
`evaluation/manifest.csv`, the file `evaluation.run_benchmark` reads."""

import csv
import hashlib
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import soundfile as sf

from app.audio.decoding import decode_mono
from app.text.arabic_normalizer import clean_whitespace

SPEAKER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
MANIFEST_FIELDS = ["audio_path", "reference", "speaker", "prompt_id", "source", "seconds", "recorded_at"]
MIN_SECONDS = 0.5

ClipSource = Literal["prompt", "free"]


class ClipRejected(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    id: str
    text: str


@dataclass(frozen=True)
class SavedClip:
    clip_id: str
    audio_path: str
    seconds: float


class ClipStore:
    def __init__(self, evaluation_dir: Path, sample_rate: int):
        self._root = evaluation_dir
        self._sample_rate = sample_rate
        self._manifest = evaluation_dir / "manifest.csv"
        self._prompts_file = evaluation_dir / "prompts" / "egyptian.txt"
        self._lock = threading.Lock()

    def prompts(self) -> list[Prompt]:
        lines = self._prompts_file.read_text(encoding="utf-8").splitlines()
        texts = [clean_whitespace(line) for line in lines if line.strip() and not line.lstrip().startswith("#")]
        # The id is derived from the sentence itself, so editing the file never re-labels old clips.
        return [Prompt(id=hashlib.sha1(text.encode()).hexdigest()[:10], text=text) for text in texts]

    def recorded_prompt_ids(self, speaker: str) -> set[str]:
        return {row["prompt_id"] for row in self._rows() if row["speaker"] == speaker and row["prompt_id"]}

    def stats(self) -> dict:
        rows = self._rows()
        return {
            "clips": len(rows),
            "seconds": round(sum(float(r["seconds"]) for r in rows), 1),
            "speakers": sorted({r["speaker"] for r in rows}),
        }

    def save(self, upload: Path, speaker: str, reference: str, prompt_id: str | None, source: ClipSource) -> SavedClip:
        if not SPEAKER_ID.match(speaker):
            raise ClipRejected("speaker must be 2-32 lowercase letters, digits, '-' or '_'.")
        reference = clean_whitespace(reference)
        if not reference:
            raise ClipRejected("reference transcript is empty.")
        if prompt_id is not None and prompt_id not in {p.id for p in self.prompts()}:
            raise ClipRejected(f"Unknown prompt '{prompt_id}'.")

        audio = decode_mono(upload, self._sample_rate)
        seconds = round(len(audio) / self._sample_rate, 2)
        if seconds < MIN_SECONDS:
            raise ClipRejected("Recording is too short.")

        clip_id = uuid.uuid4().hex[:12]
        relative = Path("audio") / speaker / f"{clip_id}.wav"
        target = self._root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        sf.write(target, audio, self._sample_rate, subtype="PCM_16")

        row = {
            "audio_path": relative.as_posix(),
            "reference": reference,
            "speaker": speaker,
            "prompt_id": prompt_id or "",
            "source": source,
            "seconds": seconds,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            is_new = not self._manifest.exists()
            with self._manifest.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
                if is_new:
                    writer.writeheader()
                writer.writerow(row)
        return SavedClip(clip_id=clip_id, audio_path=row["audio_path"], seconds=seconds)

    def _rows(self) -> list[dict]:
        if not self._manifest.exists():
            return []
        with self._manifest.open(encoding="utf-8") as handle:
            return [{field: row.get(field) or "" for field in MANIFEST_FIELDS} | {"seconds": row.get("seconds") or 0}
                    for row in csv.DictReader(handle)]
