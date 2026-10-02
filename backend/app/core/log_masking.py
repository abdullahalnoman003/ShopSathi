"""Keeps personal data and secrets out of the application logs (NFR-04, section 5.3).

Installed once per process (API and Celery worker). Every log record is rewritten when it is created, so it covers
all loggers (our own, uvicorn's access log, Celery, SQLAlchemy ...) and tracebacks too: an exception message can
carry the values of a failed SQL statement, and a request log line carries the query string. Masked: JWTs, Bearer
tokens, Facebook and encrypted tokens, ``password=`` / ``token=`` / ``code=`` style values, e-mail addresses and
phone-number-like digit runs (which also covers customer ids). Names and addresses cannot be recognised in free
text, so the code never logs message text or customer details in the first place (see the tests).
"""

import logging
import re
import traceback

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

_JWT = re.compile(r"eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{3,}")
_BEARER = re.compile(r"(?i)\bbearer\s+[\w.~+/=-]+")
_FB_TOKEN = re.compile(r"\bEAA[A-Za-z0-9]{10,}")
_ENCRYPTED = re.compile(r"\bgAAAAA[\w=-]{20,}")
_SECRET_PAIR = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|client_secret|app_secret|access_token|token|code|state|api[_-]?key|authorization|hub\.verify_token|verify_token)"
    r"""(["']?\s*[:=]\s*["']?)[^\s&"',}\]]+"""
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_NUMBER = re.compile(r"\+?[\d০-৯][\d০-৯\s-]{7,}[\d০-৯]")

#: the development-only mail log keeps the reset link readable (see EmailService); never used outside local runs
EXEMPT_LOGGERS = {"shopsathi.email.dev"}


def _numbers(m: re.Match) -> str:
    digits = sum(c.isdigit() for c in m.group(0).translate(_BANGLA_DIGITS))
    return "[number]" if digits >= 9 else m.group(0)  # dates and short counts stay readable


def mask(text: str) -> str:
    text = _JWT.sub("[jwt]", text)
    text = _BEARER.sub("Bearer [token]", text)
    text = _FB_TOKEN.sub("[fb-token]", text)
    text = _ENCRYPTED.sub("[encrypted]", text)
    text = _SECRET_PAIR.sub(lambda m: f"{m.group(1)}{m.group(2)}[masked]", text)
    text = _EMAIL.sub("[email]", text)
    return _NUMBER.sub(_numbers, text)


_installed = False


def install_log_masking() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        if record.name in EXEMPT_LOGGERS:
            return record
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            # uvicorn's access formatter unpacks these five values (client, method, path, http version, status): mask them one by one
            record.args = tuple(mask(a) if isinstance(a, str) else a for a in record.args)
            return record
        try:
            message = record.getMessage()
        except Exception:  # a broken format string must never break logging
            message = str(record.msg)
        record.msg, record.args = mask(message), ()
        if record.exc_info and record.exc_info[0] is not None and not record.exc_text:
            record.exc_text = mask("".join(traceback.format_exception(*record.exc_info)).rstrip())
        return record

    logging.setLogRecordFactory(factory)
