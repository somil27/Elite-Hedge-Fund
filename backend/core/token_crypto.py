"""
Token encryption service.
Access tokens are encrypted with AES-256-GCM before DB storage.
The encryption key is derived from SECRET_KEY in .env.
"""
import base64
import os
from typing import Optional
from core.config import settings


def _get_key() -> bytes:
    """Derive a 32-byte AES key from SECRET_KEY."""
    import hashlib
    return hashlib.sha256(settings.secret_key.encode()).digest()


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns base64-encoded ciphertext."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key   = _get_key()
        nonce = os.urandom(12)          # 96-bit nonce for GCM
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        # Prepend nonce to ciphertext, then base64-encode
        return base64.b64encode(nonce + ct).decode()
    except ImportError:
        # Fallback: base64 only (NOT secure — install cryptography)
        return base64.b64encode(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token string."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key  = _get_key()
        data = base64.b64decode(ciphertext)
        nonce, ct = data[:12], data[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode()
    except ImportError:
        return base64.b64decode(ciphertext).decode()


def maybe_decrypt(value: Optional[str]) -> Optional[str]:
    """Decrypt if not None, else return None."""
    return decrypt_token(value) if value else None
