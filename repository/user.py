import base64
import hashlib
import hmac
import os
import secrets


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def valid_csrf_token(expected: str | None, supplied: str | None) -> bool:
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def authenticate_user(user: str, password: str):
    registered_user = os.getenv("APP_USER")
    password_hash = os.getenv("APP_PASSWORD_HASH", "")
    try:
        algorithm, rounds, salt, digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = base64.urlsafe_b64decode(digest.encode())
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return bool(
        registered_user
        and hmac.compare_digest(user, registered_user)
        and hmac.compare_digest(actual, expected)
    )
