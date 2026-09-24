"""
Secure Local IPC Authentication & Token Validation
"""

import hmac
import hashlib
import time
import secrets
from typing import Optional
from src.config import settings


class IPCAuthenticator:
    """Provides HMAC-based authentication and secure session tokens for local IPC."""

    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = (secret_key or settings.ipc_secret_key).encode("utf-8")

    def generate_token(self, client_id: str = "desktop_ui", ttl_seconds: int = 3600) -> str:
        """Generates a signed time-bound session token."""
        timestamp = str(int(time.time() + ttl_seconds))
        nonce = secrets.token_hex(8)
        message = f"{client_id}:{timestamp}:{nonce}".encode("utf-8")
        signature = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
        return f"{client_id}.{timestamp}.{nonce}.{signature}"

    def validate_token(self, token: str) -> bool:
        """Validates token authenticity, signature integrity, and expiration."""
        try:
            parts = token.strip().split(".")
            if len(parts) != 4:
                return False
            client_id, timestamp_str, nonce, signature = parts
            expiry = int(timestamp_str)
            if time.time() > expiry:
                return False  # Expired

            message = f"{client_id}:{timestamp_str}:{nonce}".encode("utf-8")
            expected_sig = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected_sig)
        except Exception:
            return False

    def sign_payload(self, payload: str) -> str:
        """Generates an HMAC-SHA256 signature for an IPC payload."""
        return hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_payload_signature(self, payload: str, signature: str) -> bool:
        """Verifies payload integrity."""
        expected = self.sign_payload(payload)
        return hmac.compare_digest(signature, expected)


ipc_auth = IPCAuthenticator()
