import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from django.http import HttpResponse
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from backend.database import database
from backend.errors import APIError


SESSION_COOKIE = "tribe_quiz_session"
SESSION_DAYS = 7
PASSWORD_SCRYPT_N = 2**14
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def verify_google_credential(credential: str) -> dict:
    if not GOOGLE_CLIENT_ID:
        raise APIError(503, "Google sign-in is not configured on this server.")
    try:
        return id_token.verify_oauth2_token(credential, Request(), GOOGLE_CLIENT_ID)
    except ValueError as error:
        raise APIError(401, "Google sign-in token is invalid or expired.") from error
    except google_auth_exceptions.GoogleAuthError as error:
        raise APIError(503, "Google sign-in verification is temporarily unavailable.") from error


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=PASSWORD_SCRYPT_N, r=8, p=1, dklen=32)
    return f"{salt.hex()}:{derived.hex()}"


def password_matches(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, derived_hex = stored_hash.split(":", maxsplit=1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(derived_hex)
    except ValueError:
        return False
    actual = hashlib.scrypt(password.encode(), salt=salt, n=PASSWORD_SCRYPT_N, r=8, p=1, dklen=len(expected))
    return secrets.compare_digest(actual, expected)


def session_user_id(token: str | None) -> int | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        row = connection.execute(
            "SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
            (token_hash, now),
        ).fetchone()
    return row["user_id"] if row else None


def require_user(token: str | None) -> int:
    user_id = session_user_id(token)
    if user_id is None:
        raise APIError(401, "Please sign in to continue.")
    return user_id


def public_user(user_id: int) -> dict:
    with database() as connection:
        row = connection.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise APIError(401, "Please sign in to continue.")
    return dict(row)


def issue_session(user_id: int, response: HttpResponse) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with database() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), user_id, expires_at.isoformat()),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="Lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )
