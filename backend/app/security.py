"""Tokens and encryption at rest.

Every person gets a random id and a bearer token; only the token's hash is kept. Everything
personal that lives outside Elastic (the person record, cached pages, chapter prose) is
Fernet-encrypted with HEREAFTER_DATA_KEY, which is generated into .env on first use.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

from . import config

DEMO_ID, DEMO_TOKEN = "demo", "demo"
_fernet: Fernet | None = None


def fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("HEREAFTER_DATA_KEY", "").strip()
        if not key:
            key = Fernet.generate_key().decode()
            os.environ["HEREAFTER_DATA_KEY"] = key
            env_path = config.ROOT / ".env"
            with env_path.open("a") as f:
                f.write(f"\n# Encrypts personal data at rest (person record, page cache, chapters). Losing it loses them.\nHEREAFTER_DATA_KEY={key}\n")
            env_path.chmod(0o600)
        _fernet = Fernet(key.encode())
    return _fernet


def seal(text: str | None) -> str | None:
    return None if text is None else fernet().encrypt(text.encode()).decode()


def unseal(blob: str | None) -> str | None:
    if blob is None:
        return None
    try:
        return fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return None


def new_person_id() -> str:
    return "p_" + secrets.token_hex(8)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(token: str, stored_hash: str | None) -> bool:
    return bool(stored_hash) and hmac.compare_digest(token_hash(token), stored_hash)
