"""Respell Arabic text so text-to-speech models trained mostly on MSA pronounce it the Egyptian way.

The models read letters by MSA rules. Two rules that make speech sound foreign to Egyptians:

- Taa marbuta (ة) followed by another word is read as "t" (زحمةُ موت -> "zahmet mot"). In Egyptian
  it is "a" unless the next word is its possessor (ساعِت الفجر). Heuristic: keep ة before a word
  starting with "ال" (usually that construct), otherwise write ه so it is read "a".
- Qaf (ق) is a glottal stop in everyday Egyptian (نقدر -> "ne'dar"). Writing أ/ء gets that sound.
  Some formal words keep q (القرآن, قانون in formal speech), so this rule is optional.

Only for text sent to TTS; never apply it to transcripts or stored text.
"""

_TAA_MARBUTA = "ة"  # ة
_HAA = "ه"  # ه
_QAF = "ق"  # ق
_TRAILING_PUNCTUATION = "،,.!?؟:؛;\"'»)"


def _respell_taa_marbuta(text: str) -> str:
    words = text.split(" ")
    for index, word in enumerate(words):
        core = word.rstrip(_TRAILING_PUNCTUATION)
        if not core.endswith(_TAA_MARBUTA):
            continue
        ends_clause = len(core) != len(word) or index == len(words) - 1
        next_word = words[index + 1] if index + 1 < len(words) else ""
        if not ends_clause and next_word.startswith("ال"):
            continue  # construct state: Egyptian keeps the "t" (ساعة الفجر -> ساعِت الفجر)
        words[index] = core[:-1] + _HAA + word[len(core):]
    return " ".join(words)


def _respell_qaf(text: str) -> str:
    # أ is how Egyptians spell the sound in chat (نأدر، أالي), so models read it as a glottal stop.
    return text.replace(_QAF, "أ")


def egyptian_spelling(text: str, qaf_as_hamza: bool = False) -> str:
    text = _respell_taa_marbuta(text)
    if qaf_as_hamza:
        text = _respell_qaf(text)
    return text
