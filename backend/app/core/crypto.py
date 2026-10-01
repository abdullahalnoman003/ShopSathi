"""Encryption of secrets stored in the database (Facebook Page tokens, NFR-03)."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CipherError(RuntimeError):
    """The encryption key is missing or invalid, or a stored value cannot be decrypted with it."""


class TokenCipher:
    """Fernet (AES-128-CBC + HMAC) encryption with the key from FB_TOKEN_ENCRYPTION_KEY.

    The plaintext is never logged. Each encryption gives a different ciphertext.
    """

    def __init__(self, key: str | None = None) -> None:
        key = get_settings().fb_token_encryption_key if key is None else key
        if not key:
            raise CipherError("FB_TOKEN_ENCRYPTION_KEY is not set")
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as e:
            raise CipherError("FB_TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from e

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise CipherError("Could not decrypt (wrong FB_TOKEN_ENCRYPTION_KEY?)") from e
