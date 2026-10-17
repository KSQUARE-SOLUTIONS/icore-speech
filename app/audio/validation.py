import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".webm", ".flac", ".mp4"}
CHUNK_BYTES = 1024 * 1024


class AudioRejected(ValueError):
    """The upload is not acceptable audio. The message is safe to return to the client."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@contextmanager
def stored_upload(source: BinaryIO, filename: str | None, max_bytes: int) -> Iterator[Path]:
    """Copy an upload to a server-named temp file (never the client's name), enforcing the size
    limit while streaming, and delete it when the request is done."""
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AudioRejected(f"Unsupported file type '{extension or 'none'}'.", status_code=415)

    workdir = Path(tempfile.mkdtemp(prefix="icore-speech-"))
    target = workdir / f"{uuid.uuid4().hex}{extension}"
    try:
        written = 0
        with target.open("wb") as out:
            while chunk := source.read(CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise AudioRejected(f"File is larger than {max_bytes // (1024 * 1024)} MB.", status_code=413)
                out.write(chunk)
        if written == 0:
            raise AudioRejected("File is empty.")
        yield target
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def probe_duration(path: Path) -> float:
    """Open the file with FFmpeg (PyAV) to prove it really is audio, and return its length in
    seconds. The extension alone is never trusted."""
    import av

    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise AudioRejected("File has no audio stream.", status_code=415)
            if container.duration is not None:
                return container.duration / av.time_base
            stream = container.streams.audio[0]
            seconds = 0.0
            for frame in container.decode(stream):
                seconds += frame.samples / frame.sample_rate
            return seconds
    except AudioRejected:
        raise
    except Exception as exc:  # PyAV raises many error types for corrupt input
        raise AudioRejected("File could not be decoded as audio.", status_code=415) from exc


def validate_duration(path: Path, max_seconds: int) -> float:
    seconds = probe_duration(path)
    if seconds <= 0:
        raise AudioRejected("Audio is empty.")
    if seconds > max_seconds:
        raise AudioRejected(f"Audio is longer than {max_seconds} seconds.", status_code=413)
    return seconds
