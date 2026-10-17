from app.text.arabic_normalizer import normalize_arabic


def test_removes_diacritics_and_tatweel():
    assert normalize_arabic("مَرْحَبـــاً") == "مرحبا"


def test_folds_alef_ya_and_ta_marbuta():
    assert normalize_arabic("أحمد إلى آخر المدرسة") == "احمد الي اخر المدرسه"


def test_converts_arabic_indic_digits_and_strips_punctuation():
    assert normalize_arabic("الساعة ٣:٣٠، تمام؟") == "الساعه 3 30 تمام"


def test_lowercases_latin_and_collapses_spaces():
    assert normalize_arabic("  IcoreSoft   App ") == "icoresoft app"
