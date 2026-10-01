import pytest

from shopsathi_ai.validators import is_valid_bd_phone, normalize_and_validate_bd_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("01712345678", "01712345678"),
        ("  01712345678  ", "01712345678"),
        ("০১৭১২৩৪৫৬৭৮", "01712345678"),  # Bangla digits
        ("০১৭১২-৩৪৫৬৭৮", "01712345678"),
        ("017-1234-5678", "01712345678"),
        ("017 1234 5678", "01712345678"),
        ("017.1234.5678", "01712345678"),
        ("(017) 12345678", "01712345678"),
        ("+8801712345678", "01712345678"),  # +88 country code
        ("+88 01712-345678", "01712345678"),
        ("8801712345678", "01712345678"),  # 88 country code
        ("০১৩১২৩৪৫৬৭৮", "01312345678"),  # 013 is the lowest valid prefix
        ("01912345678", "01912345678"),  # 019 is the highest
        ("01812345678", "01812345678"),
    ],
)
def test_valid_numbers_are_normalised(raw, expected):
    assert normalize_and_validate_bd_phone(raw) == expected
    assert is_valid_bd_phone(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        None,
        "   ",
        "1712345678",  # 10 digits, missing the leading 0
        "0171234567",  # 10 digits
        "017123456789",  # 12 digits
        "0171234567890",  # 13 digits
        "01212345678",  # prefix 012 is not a mobile operator
        "01012345678",  # prefix 010
        "02712345678",  # not 01...
        "11712345678",
        "+8801212345678",  # right length but wrong prefix
        "+88017123456",  # too short after the country code
        "880171234567",  # 12 digits starting with 88
        "0171234567a",  # letter inside
        "phone: 01712345678",  # text around the number is not a number
        "017123 45678 9",
        "01712345678 01812345678",  # two numbers
        "০১৭১২৩৪৫৬৭",  # Bangla digits, only 9 digits
        "+8001712345678",
        "01712345678+",
        "++8801712345678",
    ],
)
def test_invalid_numbers_are_rejected(raw):
    assert normalize_and_validate_bd_phone(raw) is None
    assert not is_valid_bd_phone(raw)


def test_result_is_always_exactly_11_digits_starting_with_01():
    for raw in ["+8801912345678", "০১৫১২৩৪৫৬৭৮", "88 01612 345678"]:
        out = normalize_and_validate_bd_phone(raw)
        assert out is not None and len(out) == 11 and out.isascii() and out.isdigit() and out.startswith("01")
