"""Message style detection (Bangla script / English / Banglish) and Bangla digit normalisation."""

import re
from typing import Literal

LanguageStyle = Literal["bangla", "english", "banglish"]

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_BANGLA_LETTER = re.compile(r"[ঀ-৿]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[a-z]+")

# Common romanised-Bangla words (kept distinctive: words that are also ordinary English are left out).
_BANGLISH_WORDS = frozenset(
    """
    ache achhe nai nei koto kto dam daam taka tk hobe hoy hobey pabo pabe pawa pabo paba jabe jay
    lagbe lagche chai chaiche dibo den dian deen dite nibo nebo nite kemon kothay kothai ki keno
    ami amar apni apnar amra tomar tumi eta eita ota oita ekta ekta ta ti khana bhai vai apu
    bolen bolun bolo bolte janaben janan jante dekhan dekhao dekhte pathan pathaben pathano
    koyta koita kon kotodin kobe ekhon pore shesh bhalo valo kharap thik thikache acha accha
    jinis jiniss shob sob lal nil sobuj kalo shada holud golapi kisu kichu abar naki kina
    onek ektu apnara dhonnobad dhonnobaad shukriya
    """.split()
)
_BANGLISH_MIN_HITS = 1


def normalise_digits(text: str) -> str:
    """Bangla digits (০-৯) -> ASCII digits (0-9) so numbers and sizes can be compared."""
    return text.translate(_BANGLA_DIGITS)


def detect_style(text: str) -> LanguageStyle:
    """``bangla`` if the message is mostly Bangla script, ``banglish`` if Latin letters with Bangla words,
    otherwise ``english``."""
    bangla = len(_BANGLA_LETTER.findall(text))
    latin = len(_LATIN_LETTER.findall(text))
    if bangla and bangla >= 0.3 * (bangla + latin):
        return "bangla"
    words = _WORD.findall(text.lower())
    hits = sum(1 for w in words if w in _BANGLISH_WORDS)
    if hits >= _BANGLISH_MIN_HITS:
        return "banglish"
    return "bangla" if bangla else "english"
