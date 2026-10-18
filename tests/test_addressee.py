import pytest

from app.text.addressee import mark_addressee


@pytest.mark.parametrize(
    ("text", "female", "male"),
    [
        ("تسلم ايدك يا ماما", "تسلم ايدِك يا ماما", "تسلم ايدَك يا ماما"),
        ("أنا معاك", "أنا معاكي", "أنا معاك"),
        ("الكلام ده ليك", "الكلام ده ليكي", "الكلام ده ليك"),
        ("أبوك فين؟", "أبوكي فين؟", "أبوك فين؟"),
        ("عربيتك جميلة", "عربيتِك جميلة", "عربيتَك جميلة"),
        ("ازيك يا سامي", "إِزَّيِّك يا سامي", "ازيك يا سامي"),
        ("انت فين", "إنتي فين", "انت فين"),
    ],
)
def test_marks_second_person_endings(text, female, male):
    assert mark_addressee(text, "female") == female
    assert mark_addressee(text, "male") == male


@pytest.mark.parametrize("text", ["مبروك يا جماعة", "الملك والشباك", "ضحك قوي", "لك"])
def test_leaves_words_where_kaf_is_not_you(text):
    assert mark_addressee(text, "female") == text
    assert mark_addressee(text, "male") == text


def test_auto_and_diacritised_words_are_untouched():
    assert mark_addressee("تسلم ايدك", "auto") == "تسلم ايدك"
    assert mark_addressee("بحبَّك", "female") == "بحبَّك"
