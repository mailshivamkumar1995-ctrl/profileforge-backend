"""
Application-layer encryption for sensitive fields stored in the database.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
The key is loaded from settings.FIELD_ENCRYPTION_KEY, which must be a
URL-safe base64-encoded 32-byte key. Generate with:

    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())

Store the output in AWS Secrets Manager under the key FIELD_ENCRYPTION_KEY
and inject it as an environment variable at runtime.
"""
import logging
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def _get_fernet():
    from cryptography.fernet import Fernet, MultiFernet
    keys = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not keys:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY is not set. "
            "Cannot encrypt or decrypt sensitive fields."
        )
    # Support comma-separated list for key rotation (MultiFernet decrypts with any key,
    # encrypts with the first/primary key).
    raw_keys = [k.strip().encode() for k in str(keys).split(",") if k.strip()]
    if len(raw_keys) == 1:
        return Fernet(raw_keys[0])
    return MultiFernet([Fernet(k) for k in raw_keys])


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a URL-safe base64 ciphertext string."""
    if not plaintext:
        return plaintext
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string. Returns plaintext."""
    if not ciphertext:
        return ciphertext
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except Exception:
        logger.error("Failed to decrypt field value — key mismatch or corrupted data")
        raise ValueError("Failed to decrypt field value.")


class EncryptedTextField(models.TextField):
    """
    A TextField that transparently encrypts values before writing to the
    database and decrypts them when reading back.

    Usage:
        access_token = EncryptedTextField(blank=True)
    """

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return decrypt_value(value)
        except ValueError:
            # Log and return empty rather than crashing the application —
            # but only for read paths; write paths still raise.
            logger.error(
                "Could not decrypt db value for field %s; returning empty string",
                self.attname,
            )
            return ""

    def get_prep_value(self, value):
        if not value:
            return value
        return encrypt_value(value)
