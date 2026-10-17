import pytest

from app.text.egyptian_spelling import egyptian_spelling


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("الطريق كان زحمة موت", "الطريق كان زحمه موت"),
        ("الساعة اتناشر", "الساعه اتناشر"),
        ("ساعة الفجر", "ساعة الفجر"),  # construct state keeps the "t"
        ("عندنا اجتماع مهم الساعة.", "عندنا اجتماع مهم الساعه."),
        ("كلمة، وبعدين", "كلمه، وبعدين"),
        ("زحمة", "زحمه"),
        ("مفيش تاء مربوطة هنا؟", "مفيش تاء مربوطه هنا؟"),
    ],
)
def test_taa_marbuta_reads_as_a_except_in_construct_state(text, expected):
    assert egyptian_spelling(text) == expected


def test_qaf_becomes_hamza_only_when_asked():
    assert egyptian_spelling("نقدر نساعدك") == "نقدر نساعدك"
    assert egyptian_spelling("نقدر نساعدك", qaf_as_hamza=True) == "نأدر نساعدك"
    assert egyptian_spelling("قالي بكرة", qaf_as_hamza=True) == "أالي بكره"
