"""Password/PIN hashing and random token generation."""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_secret(raw: str) -> str:
    """Hash a password or PIN with Argon2 (NFR-1)."""
    return _hasher.hash(raw)


def verify_secret(raw: str, hashed: str | None) -> bool:
    """Verify a password/PIN against its hash. False (never raises) on mismatch or missing hash."""
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, raw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token(n_bytes: int = 32) -> str:
    """A URL-safe random token, used for session ids and CSRF tokens."""
    return secrets.token_urlsafe(n_bytes)


def hash_token(raw: str) -> str:
    """Fast, deterministic hash for high-entropy tokens (session ids).

    Session tokens are random and looked up by equality on every request, so a
    slow hash (Argon2) would be wasted work; SHA-256 is fine here because the
    input already has ~256 bits of entropy, unlike a user-chosen password.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)
