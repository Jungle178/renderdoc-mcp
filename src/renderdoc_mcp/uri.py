from __future__ import annotations

import secrets
import string

CAPTURE_ID_ALPHABET = set(string.hexdigits.lower())


def create_capture_id() -> str:
    return secrets.token_hex(16)


def normalize_capture_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized or any(char not in CAPTURE_ID_ALPHABET for char in normalized):
        raise ValueError("capture_id must be a non-empty lowercase hex string.")
    return normalized
