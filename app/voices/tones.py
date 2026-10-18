"""Tones (emotions) for cloned voices.

The cloning models copy the delivery of the reference recording, not only the timbre: a sample
read with excitement makes every generated line sound excited. So a tone is simply another
recording of the same person, stored as voice id `<person>-<tone>` (karim-excited). The plain id
(karim) is the person's normal tone."""

TONES: dict[str, str] = {
    "excited": "متحمس",
    "angry": "متعصب",
    "calm": "هادي",
    "serious": "جد",
    "sad": "حزين",
}


def voice_id_for(person: str, tone: str | None) -> str:
    return f"{person}-{tone}" if tone else person


def split_voice_id(voice_id: str) -> tuple[str, str | None]:
    """karim-excited -> ("karim", "excited"); karim -> ("karim", None)."""
    person, _, suffix = voice_id.rpartition("-")
    if person and suffix in TONES:
        return person, suffix
    return voice_id, None
