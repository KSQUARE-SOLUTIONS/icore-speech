"""Pronunciation fixes: which spelling a TTS engine should receive for a word.

Two CSV files with `word,spoken` rows:
- the base file in the repo (app/text/lexicons/voicetut_overrides.csv), shared by everyone;
- a local file (data/pronunciations.csv, git-ignored) that the web page edits.
Local rows win over base rows for the same word. Lines starting with # are comments."""

import csv
import io
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# A key is one Arabic word (a run of these letters, as VoiceTut matches words) or a phrase of such
# words separated by single spaces, for fixes that depend on context (تسلم ايدك vs تسلم على).
ARABIC_WORD_OR_PHRASE = re.compile(r"^[ء-ي]+( [ء-ي]+)*$")
MAX_SPOKEN_CHARS = 64

Source = Literal["base", "local"]


class PronunciationRejected(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Pronunciation:
    word: str
    spoken: str
    source: Source


def read_pronunciations(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    rows = {}
    for row in csv.DictReader(lines):
        word, spoken = (row.get("word") or "").strip(), (row.get("spoken") or "").strip()
        if word and spoken:
            rows[word] = spoken
    return rows


class PronunciationStore:
    def __init__(self, base_file: Path, local_file: Path):
        self._base_file = base_file
        self._local_file = local_file
        self._lock = threading.Lock()

    def entries(self) -> list[Pronunciation]:
        base, local = read_pronunciations(self._base_file), read_pronunciations(self._local_file)
        merged = {word: Pronunciation(word, spoken, "base") for word, spoken in base.items()}
        merged.update({word: Pronunciation(word, spoken, "local") for word, spoken in local.items()})
        return sorted(merged.values(), key=lambda entry: entry.word)

    def mapping(self) -> dict[str, str]:
        return {entry.word: entry.spoken for entry in self.entries()}

    def set(self, word: str, spoken: str) -> Pronunciation:
        word, spoken = " ".join(word.split()), " ".join(spoken.split())
        if not ARABIC_WORD_OR_PHRASE.match(word):
            raise PronunciationRejected("Write an Arabic word or phrase, letters only (no diacritics or punctuation).")
        if not spoken or len(spoken) > MAX_SPOKEN_CHARS:
            raise PronunciationRejected(f"Write how it should sound (1-{MAX_SPOKEN_CHARS} characters).")
        with self._lock:
            local = read_pronunciations(self._local_file)
            local[word] = spoken
            self._write_local(local)
        return Pronunciation(word, spoken, "local")

    def delete(self, word: str) -> None:
        with self._lock:
            local = read_pronunciations(self._local_file)
            if word not in local:
                if word in read_pronunciations(self._base_file):
                    raise PronunciationRejected("This is a shared fix from the repository; change it there.", 409)
                raise PronunciationRejected(f"No fix for '{word}'.", 404)
            del local[word]
            self._write_local(local)

    def _write_local(self, rows: dict[str, str]) -> None:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["word", "spoken"])
        writer.writerows(sorted(rows.items()))
        self._local_file.parent.mkdir(parents=True, exist_ok=True)
        self._local_file.write_text(buffer.getvalue(), encoding="utf-8")
