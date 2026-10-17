"""Arabic text normalisation for *evaluation and search only*.

The API always returns the raw transcript. These rules fold spelling variants so that WER/CER
measure recognition mistakes rather than spelling choices; they must never be applied to text
shown to a user as if it were what they said.
"""

import re
import unicodedata

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_ALEF_VARIANTS = re.compile(r"[آأإٱ]")  # آ أ إ ٱ -> ا
_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACES = re.compile(r"\s+")
_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def clean_whitespace(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def normalize_arabic(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _DIACRITICS.sub("", text)
    text = text.replace(_TATWEEL, "")
    text = _ALEF_VARIANTS.sub("ا", text)
    text = text.replace("ى", "ي")  # ى -> ي
    text = text.replace("ة", "ه")  # ة -> ه
    text = text.translate(_ARABIC_INDIC_DIGITS)
    text = _PUNCTUATION.sub(" ", text)
    return clean_whitespace(text.lower())
