import hashlib
import hmac
import json
import logging
import mimetypes
import re
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from pydantic import ValidationError

from backend.database import INTEGRITY_ERRORS, database
from backend.errors import APIError
from backend.mailer import (
    APP_BASE_URL,
    EmailDeliveryError,
    is_configured as is_mail_configured,
    send_account_verification_email,
    send_password_reset_email,
)
from backend.question_generator import (
    QUESTION_COUNT,
    QUESTION_IMAGE_REFERENCES,
    questions_for_culture,
    select_quiz_questions,
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


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
logger = logging.getLogger(__name__)
RESET_TOKEN_LIFETIME = timedelta(hours=1)
RESET_REQUEST_COOLDOWN = timedelta(seconds=60)
VERIFICATION_TOKEN_LIFETIME = timedelta(hours=24)
VERIFICATION_REQUEST_COOLDOWN = timedelta(seconds=60)
FRONTEND_FILES = {
    "index.html",
    "auth.html",
    "forgot-password.html",
    "reset-password.html",
    "verify-email.html",
    "styles.css",
    "api.js",
    "app.js",
    "auth.js",
    "forgot-password.js",
    "reset-password.js",
    "verify-email.js",
    "leaderboard.html",
    "leaderboard.js",
}
PROFILE_FILES = {
    "afrikaans.png",
    "ndebele.webp",
    "sepedi.webp",
    "sesotho.webp",
    "swahili.png",
    "swati.webp",
    "tsonga.webp",
    "tswana.webp",
    "vhenda.webp",
    "xhosa.webp",
    "zulu.webp",
}


def api_endpoint(method: str):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method != method:
                response = JsonResponse({"detail": "Method not allowed."}, status=405)
                response["Allow"] = method
                return response
            try:
                return view(request, *args, **kwargs)
            except APIError as error:
                return JsonResponse({"detail": error.detail}, status=error.status_code)

        return wrapped

    return decorate


def parse_payload(request, schema):
    try:
        body = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise APIError(400, "Request body must be valid JSON.") from error
    try:
        return schema.model_validate(body)
    except ValidationError as error:
        details = [
            {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
            for item in error.errors()
        ]
        raise APIError(422, details) from error


def json_response(data: dict, status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status)


@api_endpoint("GET")
def health(request):
    return json_response({"status": "ok"})


@api_endpoint("GET")
def get_quiz(request):
    with database() as connection:
        cultures = [dict(row) for row in connection.execute("SELECT * FROM cultures ORDER BY id")]
        questions = [
            dict(row)
            for row in connection.execute(
                "SELECT id, prompt, options_json, note FROM questions ORDER BY id"
            )
        ]
    for question in questions:
        question["options"] = json.loads(question.pop("options_json"))
    return json_response({"cultures": cultures, "questions": questions})


@api_endpoint("POST")
def signup(request):
    payload = parse_payload(request, SignupRequest)
    if not is_mail_configured():
        raise APIError(503, "Email verification is not configured on this server.")
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise APIError(400, "Enter a valid email address.")
    name = payload.name.strip()
    if not name:
        raise APIError(400, "Add a display name to create your account.")

    now = datetime.now(timezone.utc)
    with database() as connection:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise APIError(409, "An account with that email already exists.")
        connection.execute("DELETE FROM pending_signups WHERE expires_at <= ?", (now.isoformat(),))
        pending = connection.execute(
            "SELECT created_at FROM pending_signups WHERE email = ?",
            (email,),
        ).fetchone()
        if pending and datetime.fromisoformat(pending["created_at"]) > now - VERIFICATION_REQUEST_COOLDOWN:
            return json_response(
                {"message": "If this email can be registered, a verification link was sent. Check your inbox or try again shortly."},
                status=202,
            )

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
    except (EmailDeliveryError, OSError, smtplib.SMTPException) as error:
        logger.exception("Could not send an account verification email.")
        with database() as connection:
            connection.execute(
                "DELETE FROM pending_signups WHERE email = ? AND token_hash = ?",
                (email, token_hash),
            )
        raise APIError(503, "Could not send the verification email. Please try again later.") from error
    return json_response(
        {"message": "Verification email sent. Open the link in your email to activate your account."},
        status=202,
    )


@api_endpoint("POST")
def verify_email(request):
    payload = parse_payload(request, VerifyEmailRequest)
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
                raise APIError(400, "This verification link is invalid or has expired.")
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (pending["name"], pending["email"], pending["password_hash"], now),
            )
            user_id = cursor.lastrowid
            connection.execute("DELETE FROM pending_signups WHERE email = ?", (pending["email"],))
    except INTEGRITY_ERRORS as error:
        raise APIError(409, "An account with that email already exists.") from error

    response = json_response({"user": public_user(user_id)})
    issue_session(user_id, response)
    return response


@api_endpoint("POST")
def signin(request):
    payload = parse_payload(request, LoginRequest)
    email = payload.email.strip().lower()
    with database() as connection:
        user = connection.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not password_matches(payload.password, user["password_hash"]):
        raise APIError(401, "Email or password is incorrect.")
    response = json_response({"user": public_user(user["id"])})
    issue_session(user["id"], response)
    return response


@api_endpoint("POST")
def forgot_password(request):
    payload = parse_payload(request, ForgotPasswordRequest)
    if not is_mail_configured():
        raise APIError(503, "Password reset email is not configured on this server.")

    response_message = (
        "If an account matches, a reset link will be sent if email delivery succeeds. "
        "Check your spam folder, and contact the site administrator if it does not arrive."
    )
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return json_response({"message": response_message})
    now = datetime.now(timezone.utc)
    with database() as connection:
        user = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            return json_response({"message": response_message})

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
            return json_response({"message": response_message})

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        connection.execute(
            "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, (now + RESET_TOKEN_LIFETIME).isoformat(), now.isoformat()),
        )

    reset_url = f"{APP_BASE_URL}/reset-password.html?token={token}"
    try:
        send_password_reset_email(email, reset_url)
    except (EmailDeliveryError, OSError, smtplib.SMTPException):
        logger.exception("Could not send a password reset email.")
        with database() as connection:
            connection.execute("DELETE FROM password_reset_tokens WHERE token_hash = ?", (token_hash,))
    else:
        with database() as connection:
            connection.execute(
                "DELETE FROM password_reset_tokens WHERE user_id = ? AND token_hash != ?",
                (user_id, token_hash),
            )
    return json_response({"message": response_message})


@api_endpoint("POST")
def reset_password(request):
    payload = parse_payload(request, ResetPasswordRequest)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        reset_token = connection.execute(
            "SELECT user_id FROM password_reset_tokens WHERE token_hash = ? AND expires_at > ?",
            (token_hash, now),
        ).fetchone()
        if reset_token is None:
            raise APIError(400, "This reset link is invalid or has expired.")
        user_id = reset_token["user_id"]
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(payload.password), user_id),
        )
        connection.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return json_response({"status": "ok"})


@api_endpoint("GET")
def google_auth_config(request):
    return json_response({"enabled": bool(GOOGLE_CLIENT_ID), "client_id": GOOGLE_CLIENT_ID or None})


@api_endpoint("POST")
def google_signin(request):
    payload = parse_payload(request, GoogleLoginRequest)
    claims = verify_google_credential(payload.credential)
    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, payload.nonce):
        raise APIError(401, "Google sign-in token could not be verified.")
    email_claim = claims.get("email")
    if not isinstance(email_claim, str) or not email_claim.strip() or claims.get("email_verified") is not True:
        raise APIError(401, "Google must verify your email address to continue.")
    email = email_claim.strip().lower()

    name = str(claims.get("name") or email.split("@", maxsplit=1)[0]).strip()[:80]
    with database() as connection:
        user = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, hash_password(secrets.token_urlsafe(32)), datetime.now(timezone.utc).isoformat()),
            )
            user_id = cursor.lastrowid
        else:
            user_id = user["id"]
    response = json_response({"user": public_user(user_id)})
    issue_session(user_id, response)
    return response


@api_endpoint("GET")
def get_current_user(request):
    user_id = require_user(request.COOKIES.get(SESSION_COOKIE))
    return json_response({"user": public_user(user_id)})


@api_endpoint("POST")
def signout(request):
    token = request.COOKIES.get(SESSION_COOKIE)
    if token:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with database() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    response = json_response({"status": "ok"})
    response.set_cookie(
        SESSION_COOKIE,
        "",
        max_age=0,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="Lax",
    )
    return response


@api_endpoint("POST")
def start_attempt(request):
    payload = parse_payload(request, StartAttemptRequest)
    user_id = require_user(request.COOKIES.get(SESSION_COOKIE))
    with database() as connection:
        culture_row = connection.execute(
            "SELECT id, name, language, region FROM cultures WHERE id = ?",
            (payload.culture_id,),
        ).fetchone()
    if culture_row is None:
        raise APIError(404, "Culture not found.")

    culture = dict(culture_row)
    question_pool, question_source = questions_for_culture(culture)
    if question_source == "unavailable":
        raise APIError(
            503,
            f"Tribe-specific questions for {culture['name']} are unavailable. "
            "Configure GEMINI_API_KEY and try again.",
        )
    try:
        selected_questions = select_quiz_questions(question_pool)
    except ValueError as error:
        raise APIError(503, "This culture does not have enough quiz questions yet.") from error

    attempt_id = str(uuid.uuid4())
    public_questions = []
    with database() as connection:
        connection.execute(
            "INSERT INTO attempts (id, user_id, culture_id, question_count, started_at) VALUES (?, ?, ?, ?, ?)",
            (
                attempt_id,
                user_id,
                payload.culture_id,
                QUESTION_COUNT,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        for question_order, question in enumerate(selected_questions):
            cursor = connection.execute(
                """INSERT INTO quiz_attempt_questions
                   (attempt_id, question_order, culture_question_id, prompt, options_json,
                    correct_index, note, category, image_url, image_search_term,
                    image_credit, image_source_url, image_license, image_license_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt_id,
                    question_order,
                    question["id"],
                    question["prompt"],
                    json.dumps(question["options"], ensure_ascii=False),
                    question["correct_index"],
                    question["note"],
                    question["category"],
                    question["image_url"],
                    question["image_search_term"],
                    question["image_credit"],
                    question["image_source_url"],
                    question["image_license"],
                    question["image_license_url"],
                ),
            )
            public_questions.append(
                {
                    "id": cursor.lastrowid,
                    "prompt": question["prompt"],
                    "options": question["options"],
                    "category": question["category"],
                    "image_url": question["image_url"],
                    "image_search_term": question["image_search_term"],
                    "image_credit": question["image_credit"],
                    "image_source_url": question["image_source_url"],
                    "image_license": question["image_license"],
                    "image_license_url": question["image_license_url"],
                }
            )
    return json_response(
        {
            "attempt_id": attempt_id,
            "question_count": QUESTION_COUNT,
            "questions": public_questions,
            "question_source": question_source,
        },
        status=201,
    )


@api_endpoint("POST")
def submit_answer(request, attempt_id: str):
    payload = parse_payload(request, AnswerRequest)
    with database() as connection:
        attempt = connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
        if attempt is None:
            raise APIError(404, "Quiz attempt not found.")
        user_id = session_user_id(request.COOKIES.get(SESSION_COOKIE))
        if (attempt["user_id"] is not None and attempt["user_id"] != user_id) or attempt["completed_at"]:
            raise APIError(403, "This quiz attempt is not available.")
        answered_count = connection.execute(
            "SELECT COUNT(*) FROM quiz_attempt_answers WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()[0]
        question = connection.execute(
            """SELECT * FROM quiz_attempt_questions
               WHERE attempt_id = ? AND question_order = ?""",
            (attempt_id, answered_count),
        ).fetchone()
        if question is None or question["id"] != payload.question_id:
            raise APIError(409, "Answer the questions in order, one at a time.")
        correct = payload.selected_index == question["correct_index"]
        correct_count = attempt["correct_count"] + int(correct)
        score = correct_count * 10
        answered_count += 1
        completed_at = (
            datetime.now(timezone.utc).isoformat()
            if answered_count == attempt["question_count"]
            else None
        )
        connection.execute(
            """INSERT INTO quiz_attempt_answers
               (attempt_id, attempt_question_id, selected_index, is_correct)
               VALUES (?, ?, ?, ?)""",
            (attempt_id, question["id"], payload.selected_index, int(correct)),
        )
        connection.execute(
            "UPDATE attempts SET correct_count = ?, score = ?, completed_at = ? WHERE id = ?",
            (correct_count, score, completed_at, attempt_id),
        )
    return json_response(
        {
            "correct": correct,
            "correct_index": question["correct_index"],
            "note": question["note"],
            "score": score,
            "correct_count": correct_count,
            "answered_count": answered_count,
            "completed": completed_at is not None,
        }
    )


@api_endpoint("GET")
def get_user_attempts(request):
    user_id = require_user(request.COOKIES.get(SESSION_COOKIE))
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
    return json_response({"attempts": attempts})


@api_endpoint("GET")
def get_leaderboard(request):
    user_id = session_user_id(request.COOKIES.get(SESSION_COOKIE))
    with database() as connection:
        rows = connection.execute(
            """WITH player_totals AS (
                   SELECT users.id AS user_id, users.name AS user_name,
                          COALESCE(SUM(attempts.score), 0) AS score,
                          COALESCE(SUM(attempts.correct_count), 0) AS correct_count,
                          COALESCE(SUM(attempts.question_count), 0) AS question_count,
                          COUNT(attempts.id) AS quizzes_played
                   FROM users
                   LEFT JOIN attempts
                       ON attempts.user_id = users.id
                      AND attempts.completed_at IS NOT NULL
                   GROUP BY users.id, users.name
               ),
               ranked_players AS (
                   SELECT player_totals.*,
                          ROW_NUMBER() OVER (
                              ORDER BY score DESC, user_id ASC
                          ) AS rank
                   FROM player_totals
               )
               SELECT user_name, score, correct_count, question_count,
                      quizzes_played, rank,
                      CASE WHEN ? IS NOT NULL AND user_id = ? THEN 1 ELSE 0 END AS is_current_user
               FROM ranked_players
               ORDER BY rank""",
            (user_id, user_id),
        ).fetchall()
    scores = [dict(row) for row in rows]
    current_player = next((entry for entry in scores if entry["is_current_user"]), None)
    return json_response(
        {
            "scores": scores,
            "current_rank": current_player["rank"] if current_player else None,
            "player_count": len(scores),
            "is_signed_in": user_id is not None,
        }
    )


@ensure_csrf_cookie
def serve_frontend(request, filename: str):
    if filename not in FRONTEND_FILES:
        raise Http404
    path = FRONTEND_DIR / filename
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path.open("rb"), content_type=content_type)


@ensure_csrf_cookie
def serve_profile(request, filename: str):
    if filename not in PROFILE_FILES:
        raise Http404
    path = FRONTEND_DIR / "TribeProfile" / filename
    if not path.is_file():
        raise Http404
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path.open("rb"), content_type=content_type)


@ensure_csrf_cookie
def serve_quiz_image(request, folder: str, filename: str):
    image_reference = f"public/{folder}/{filename}"
    if image_reference not in QUESTION_IMAGE_REFERENCES:
        raise Http404
    path = FRONTEND_DIR / "quiz pictures" / folder / filename
    if not path.is_file():
        raise Http404
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path.open("rb"), content_type=content_type)
