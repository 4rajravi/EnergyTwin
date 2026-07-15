from __future__ import annotations

import os
import hashlib
import hmac
from http.client import HTTPMessage


AUTH_TOKEN_ENV = "ENERGYTWIN_AUTH_TOKEN"
AUTH_TOKEN_SHA256_ENV = "ENERGYTWIN_AUTH_TOKEN_SHA256"


def auth_enabled() -> bool:
    return bool(os.getenv(AUTH_TOKEN_ENV) or os.getenv(AUTH_TOKEN_SHA256_ENV))


def auth_status() -> dict[str, bool | str]:
    return {"enabled": auth_enabled(), "method": "bearer-token" if auth_enabled() else "none"}


def request_authorized(headers: HTTPMessage, query: dict[str, list[str]]) -> bool:
    if not auth_enabled():
        return True
    provided_tokens = _provided_tokens(headers, query)
    if not provided_tokens:
        return False
    return any(_token_matches(token) for token in provided_tokens)


def _token_matches(provided: str) -> bool:
    expected = os.getenv(AUTH_TOKEN_ENV)
    if expected and hmac.compare_digest(provided, expected):
        return True
    expected_hash = os.getenv(AUTH_TOKEN_SHA256_ENV)
    if expected_hash:
        provided_hash = hashlib.sha256(provided.encode("utf-8")).hexdigest()
        return hmac.compare_digest(provided_hash, expected_hash)
    return False


def _provided_tokens(headers: HTTPMessage, query: dict[str, list[str]]) -> list[str]:
    tokens: list[str] = []
    authorization = headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        tokens.append(authorization.removeprefix("Bearer ").strip())
    tokens.extend(value for value in query.get("token", []) if value)
    return tokens
