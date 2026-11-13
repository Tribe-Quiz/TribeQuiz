import hashlib
import hmac
import json
import logging
import re
import secrets
import smtplib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, HTTPException, Response

from backend.database import database
from backend.mailer import (
    APP_BASE_URL,
    is_configured as is_mail_configured,
    send_account_verification_email,
    send_password_reset_email,
)
from backend.schemas import (
    AnswerRequest,
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    StartAttemptRequest,
    VerifyEmailRequest,
)
from backend.security import (
    COOKIE_SECURE,
    GOOGLE_CLIENT_ID,
    SESSION_COOKIE,
    hash_password,
    issue_session,
    password_matches,
    public_user,
    require_user,
    session_user_id,
    verify_google_credential,
)


router = APIRouter()
logger = logging.getLogger(__name__)
RESET_TOKEN_LIFETIME = timedelta(hours=1)
RESET_REQUEST_COOLDOWN = timedelta(seconds=60)
VERIFICATION_TOKEN_LIFETIME = timedelta(hours=24)
VERIFICATION_REQUEST_COOLDOWN = timedelta(seconds=60)


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/quiz")
def get_quiz() -> dict:
    with database() as connection:
        cultures = [dict(row) for row in connection.execute("SELECT * FROM cultures ORDER BY id")]
        questions = [dict(row) for row in connection.execute("SELECT id, prompt, options_json, note FROM questions ORDER BY id")]
    for question in questions:
        question["options"] = json.loads(question.pop("options_json"))
    return {"cultures": cultures, "questions": questions}


@router.post("/api/auth/signup", status_code=202)
def signup(payload: SignupRequest) -> dict:
    if not is_mail_configured():
        raise HTTPException(status_code=503, detail="Email verification is not configured on this server.")
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Add a display name to create your account.")
    now = datetime.now(timezone.utc)
    with database() as connection:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with that email already exists.")
        connection.execute("DELETE FROM pending_signups WHERE expires_at <= ?", (now.isoformat(),))
        pending = connection.execute(
            "SELECT created_at FROM pending_signups WHERE email = ?",
            (email,),
        ).fetchone()
        if pending and datetime.fromisoformat(pending["created_at"]) > now - VERIFICATION_REQUEST_COOLDOWN:
            return {"message": "If this email can be registered, a verification link was sent. Check your inbox or try again shortly."}

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        connection.execute(
            """INSERT INTO pending_signups
               (email, name, password_hash, token_hash, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET
                   name = excluded.name,
                   password_hash = excluded.password_hash,
                   token_hash = excluded.token_hash,
                   expires_at = excluded.expires_at,
                   created_at = excluded.created_at""",
            (
                email,
                name,
                hash_password(payload.password),
                token_hash,
                (now + VERIFICATION_TOKEN_LIFETIME).isoformat(),
                now.isoformat(),
            ),
        )

    verification_url = f"{APP_BASE_URL}/verify-email.html?token={token}"
    try:
        send_account_verification_email(email, verification_url)
    except (OSError, smtplib.SMTPException) as error:
        logger.exception("Could not send an account verification email.")
        with database() as connection:
            connection.execute(
                "DELETE FROM pending_signups WHERE email = ? AND token_hash = ?",
                (email, token_hash),
            )
        raise HTTPException(status_code=503, detail="Could not send the verification email. Please try again later.") from error
    return {"message": "Verification email sent. Open the link in your email to activate your account."}


@router.post("/api/auth/verify-email")
def verify_email(payload: VerifyEmailRequest, response: Response) -> dict:
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    try:
        with database() as connection:
            pending = connection.execute(
                """SELECT email, name, password_hash FROM pending_signups
                   WHERE token_hash = ? AND expires_at > ?""",
                (token_hash, now),
            ).fetchone()
            if pending is None:
                raise HTTPException(status_code=400, detail="This verification link is invalid or has expired.")
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (pending["name"], pending["email"], pending["password_hash"], now),
            )
            user_id = cursor.lastrowid
            connection.execute("DELETE FROM pending_signups WHERE email = ?", (pending["email"],))
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="An account with that email already exists.") from error

    issue_session(user_id, response)
    return {"user": public_user(user_id)}


@router.post("/api/auth/signin")
def signin(payload: LoginRequest, response: Response) -> dict:
    email = payload.email.strip().lower()
    with database() as connection:
        user = connection.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not password_matches(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    issue_session(user["id"], response)
    return {"user": public_user(user["id"])}


@router.post("/api/auth/forgot-password")
def forgot_password(payload: ForgotPasswordRequest) -> dict:
    if not is_mail_configured():
        raise HTTPException(status_code=503, detail="Password reset email is not configured on this server.")

    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return {"message": "If an account exists for that email, a reset link has been sent."}
    now = datetime.now(timezone.utc)
    with database() as connection:
        user = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            return {"message": "If an account exists for that email, a reset link has been sent."}

        user_id = user["id"]
        connection.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ? AND expires_at <= ?",
            (user_id, now.isoformat()),
        )
        recent_token = connection.execute(
            "SELECT 1 FROM password_reset_tokens WHERE user_id = ? AND created_at > ?",
            (user_id, (now - RESET_REQUEST_COOLDOWN).isoformat()),
        ).fetchone()
        if recent_token is not None:
            return {"message": "If an account exists for that email, a reset link has been sent."}

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        connection.execute(
            "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (
                token_hash,
                user_id,
                (now + RESET_TOKEN_LIFETIME).isoformat(),
                now.isoformat(),
            ),
        )

    reset_url = f"{APP_BASE_URL}/reset-password.html?token={token}"
    try:
        send_password_reset_email(email, reset_url)
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send a password reset email.")
        with database() as connection:
            connection.execute("DELETE FROM password_reset_tokens WHERE token_hash = ?", (token_hash,))
    else:
        with database() as connection:
            connection.execute(
                "DELETE FROM password_reset_tokens WHERE user_id = ? AND token_hash != ?",
                (user_id, token_hash),
            )
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordRequest) -> dict:
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        reset_token = connection.execute(
            "SELECT user_id FROM password_reset_tokens WHERE token_hash = ? AND expires_at > ?",
            (token_hash, now),
        ).fetchone()
        if reset_token is None:
            raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
        user_id = reset_token["user_id"]
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(payload.password), user_id),
        )
        connection.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"status": "ok"}


@router.get("/api/auth/google/config")
def google_auth_config() -> dict:
    return {"enabled": bool(GOOGLE_CLIENT_ID), "client_id": GOOGLE_CLIENT_ID or None}


@router.post("/api/auth/google")
def google_signin(payload: GoogleLoginRequest, response: Response) -> dict:
    claims = verify_google_credential(payload.credential)
    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, payload.nonce):
        raise HTTPException(status_code=401, detail="Google sign-in token could not be verified.")
    email_claim = claims.get("email")
    if not isinstance(email_claim, str) or not email_claim.strip() or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google must verify your email address to continue.")
    email = email_claim.strip().lower()

    name = str(claims.get("name") or email.split("@", maxsplit=1)[0]).strip()[:80]
    with database() as connection:
        user = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (
                    name,
                    email,
                    hash_password(secrets.token_urlsafe(32)),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            user_id = cursor.lastrowid
        else:
            user_id = user["id"]
    issue_session(user_id, response)
    return {"user": public_user(user_id)}


@router.get("/api/auth/me")
def get_current_user(tribe_quiz_session: str | None = Cookie(default=None)) -> dict:
    return {"user": public_user(require_user(tribe_quiz_session))}


@router.post("/api/auth/signout")
def signout(response: Response, tribe_quiz_session: str | None = Cookie(default=None)) -> dict:
    if tribe_quiz_session:
        token_hash = hashlib.sha256(tribe_quiz_session.encode()).hexdigest()
        with database() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return {"status": "ok"}


@router.post("/api/attempts", status_code=201)
def start_attempt(
    payload: StartAttemptRequest,
    tribe_quiz_session: str | None = Cookie(default=None),
) -> dict:
    attempt_id = str(uuid.uuid4())
    with database() as connection:
        culture = connection.execute("SELECT id FROM cultures WHERE id = ?", (payload.culture_id,)).fetchone()
        if culture is None:
            raise HTTPException(status_code=404, detail="Culture not found.")
        question_count = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        connection.execute(
            "INSERT INTO attempts (id, user_id, culture_id, question_count, started_at) VALUES (?, ?, ?, ?, ?)",
            (attempt_id, session_user_id(tribe_quiz_session), payload.culture_id, question_count, datetime.now(timezone.utc).isoformat()),
        )
    return {"attempt_id": attempt_id, "question_count": question_count}


@router.post("/api/attempts/{attempt_id}/answers")
def submit_answer(
    attempt_id: str,
    payload: AnswerRequest,
    tribe_quiz_session: str | None = Cookie(default=None),
) -> dict:
    with database() as connection:
        attempt = connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
        if attempt is None:
            raise HTTPException(status_code=404, detail="Quiz attempt not found.")
        user_id = session_user_id(tribe_quiz_session)
        if (attempt["user_id"] is not None and attempt["user_id"] != user_id) or attempt["completed_at"]:
            raise HTTPException(status_code=403, detail="This quiz attempt is not available.")
        answered_count = connection.execute(
            "SELECT COUNT(*) FROM attempt_answers WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()[0]
        question = connection.execute(
            "SELECT * FROM questions ORDER BY id LIMIT 1 OFFSET ?", (answered_count,)
        ).fetchone()
        if question is None or question["id"] != payload.question_id:
            raise HTTPException(status_code=409, detail="Answer the questions in order, one at a time.")
        correct = payload.selected_index == question["correct_index"]
        correct_count = attempt["correct_count"] + int(correct)
        score = correct_count * 10
        answered_count += 1
        completed_at = datetime.now(timezone.utc).isoformat() if answered_count == attempt["question_count"] else None
        connection.execute(
            "INSERT INTO attempt_answers (attempt_id, question_id, selected_index, is_correct) VALUES (?, ?, ?, ?)",
            (attempt_id, question["id"], payload.selected_index, int(correct)),
        )
        connection.execute(
            "UPDATE attempts SET correct_count = ?, score = ?, completed_at = ? WHERE id = ?",
            (correct_count, score, completed_at, attempt_id),
        )
    return {
        "correct": correct,
        "correct_index": question["correct_index"],
        "note": question["note"],
        "score": score,
        "correct_count": correct_count,
        "answered_count": answered_count,
        "completed": completed_at is not None,
    }


@router.get("/api/auth/attempts")
def get_user_attempts(tribe_quiz_session: str | None = Cookie(default=None)) -> dict:
    user_id = require_user(tribe_quiz_session)
    with database() as connection:
        attempts = [
            dict(row)
            for row in connection.execute(
                """SELECT attempts.id, cultures.name AS culture, attempts.score,
                          attempts.correct_count, attempts.question_count,
                          attempts.started_at, attempts.completed_at
                   FROM attempts JOIN cultures ON cultures.id = attempts.culture_id
                   WHERE attempts.user_id = ? ORDER BY attempts.started_at DESC""",
                (user_id,),
            )
        ]
    return {"attempts": attempts}
