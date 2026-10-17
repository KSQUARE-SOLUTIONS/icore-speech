import io
from typing import Literal

import numpy as np
import soundfile as sf

AudioFormat = Literal["wav", "mp3"]

MEDIA_TYPES: dict[str, str] = {"wav": "audio/wav", "mp3": "audio/mpeg"}


def encode(audio: np.ndarray, sample_rate: int, fmt: AudioFormat) -> bytes:
    buffer = io.BytesIO()
    if fmt == "mp3":
        sf.write(buffer, audio, sample_rate, format="MP3")
    else:
        sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()
