"""Mark second-person endings for the person being addressed.

Written Egyptian Arabic does not show who is addressed: ايدك is "eedak" to a man and "eedik" to a
woman, معاك is "ma3ak" or "ma3aki". TTS models guess, usually masculine. Given the addressee, this
adds the missing vowel to words ending in the pronoun ك:

- after a consonant: kasra for a woman (ايدك -> ايدِك), fatha for a man (ايدك -> ايدَك);
- after a long vowel ا/و/ي: a woman gets ي appended (معاك -> معاكي, ليك -> ليكي, أبوك -> أبوكي);
  a man is left as is, since that is already read "ak".
Plus انت/إنت -> إنتي for a woman.

Words the caller already diacritised are left alone. Adjectives and verbs that change spelling with
gender (عامل/عاملة) are not touched: write them the way they are said.
"""

import re
from typing import Literal

Addressee = Literal["auto", "male", "female"]

_WORD = re.compile(r"[ء-ي]+")
_HARAKAT = re.compile("[ً-ْ]")
_KAF = "ك"
_LONG_VOWELS = "اوي"
_KASRA, _FATHA = "ِ", "َ"

# Words ending in ك where the ك is part of the word, not "you".
_NOT_PRONOUN = {
    "ملك", "شباك", "مبروك", "ضحك", "سمك", "بنك", "شك", "فك", "ديك", "سلك", "مسك", "ترك", "حرك",
    "بارك", "تبارك", "اشترك", "شارك", "شريك", "شبك", "كعك", "دك", "ذلك", "كذلك", "هناك", "هنالك",
    "تلك", "فلك", "هلك", "مسواك", "ماك", "باك", "بلاك", "لوك", "بوك", "فيسبوك", "تيك", "توك", "شيك",
    "ستيك", "كوك", "بيبسيكو", "تريك", "سموك", "لينك", "بلوك", "تانك", "سكوك", "صكوك",
    "سلوك", "ملوك", "شكوك", "بنوك", "مشترك", "متحرك", "معارك", "مدرك", "ممالك", "مسالك",
}
# A word with the article never carries a possessive "you" (الكتاب, never الكتابك).
_DEFINITE = ("ال", "وال", "بال", "فال", "كال", "لل")
_CONJUNCTIONS = ("و", "ف", "ب")
# Exact forms that the rules above would get wrong.
_FEMININE = {"ازيك": "إِزَّيِّك", "إزيك": "إِزَّيِّك", "انت": "إنتي", "إنت": "إنتي"}


def _mark(word: str, addressee: Addressee) -> str:
    if _HARAKAT.search(word):
        return word
    if addressee == "female" and word in _FEMININE:
        return _FEMININE[word]
    if not word.endswith(_KAF) or len(word) < 3 or word.startswith(_DEFINITE):
        return word
    if word in _NOT_PRONOUN or (word[0] in _CONJUNCTIONS and word[1:] in _NOT_PRONOUN):
        return word
    before = word[-2]
    if before in _LONG_VOWELS:
        return word + "ي" if addressee == "female" else word
    vowel = _KASRA if addressee == "female" else _FATHA
    return word[:-1] + vowel + _KAF


def mark_addressee(text: str, addressee: Addressee) -> str:
    if addressee == "auto":
        return text
    return _WORD.sub(lambda match: _mark(match.group(0), addressee), text)
