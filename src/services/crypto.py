"""
Symmetric encryption for sensitive text fields (wish titles).

Uses Fernet (AES-128-CBC + HMAC-SHA256).
The key is loaded once from config and reused for the lifetime of the process.

Encrypt before writing to DB, decrypt after reading from DB.
If a value cannot be decrypted (e.g. legacy plain-text rows) the original
string is returned unchanged so the app degrades gracefully on first deploy.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from src.config import config

logger = logging.getLogger(__name__)

_fernet: Fernet = Fernet(config.ENCRYPTION_KEY.encode())


def encrypt(text: str) -> str:
    """Return the Fernet-encrypted, URL-safe base64 string."""
    return _fernet.encrypt(text.encode()).decode()


def decrypt(text: str) -> str:
    """
    Return the decrypted plaintext.
    Falls back to the original value for rows written before encryption
    was enabled (so a zero-downtime migration is possible).
    """
    try:
        return _fernet.decrypt(text.encode()).decode()
    except (InvalidToken, Exception):
        logger.warning("Could not decrypt value — returning raw (legacy row?)")
        return text
