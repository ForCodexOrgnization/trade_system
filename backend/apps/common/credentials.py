import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _credential_cipher() -> Fernet:
    seed = getattr(settings, "IBKR_CREDENTIAL_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    if not seed:
        raise ImproperlyConfigured("An IBKR credential encryption key is required.")
    key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_credential(value: str) -> str:
    if not value:
        return ""
    return _credential_cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str) -> str:
    if not value:
        return ""
    try:
        return _credential_cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ImproperlyConfigured(
            "Unable to decrypt the IBKR token. Check IBKR_CREDENTIAL_ENCRYPTION_KEY."
        ) from exc
