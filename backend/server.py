import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "backend" / "tribe_quiz.db"))
FRONTEND_PATH = BASE_DIR / "frontend"
SESSION_COOKIE = "tribe_quiz_session"
SESSION_DAYS = 7
PASSWORD_SCRYPT_N = 2**14
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

CULTURES = [
    {"name": "Zulu", "language": "IsiZulu", "region": "South Africa", "image": "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80"},
    {"name": "Xhosa", "language": "IsiXhosa", "region": "South Africa", "image": "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80"},
    {"name": "Sesotho", "language": "Sesotho", "region": "Lesotho · South Africa", "image": "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=700&q=80"},
    {"name": "Sepedi", "language": "Sesotho sa Leboa", "region": "South Africa", "image": "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?auto=format&fit=crop&w=700&q=80"},
    {"name": "Tswana", "language": "Setswana", "region": "Botswana · South Africa", "image": "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80"},
    {"name": "Tsonga", "language": "itsonga", "region": "Southern Africa", "image": "https://images.unsplash.com/photo-1523805009345-7448845a9e53?auto=format&fit=crop&w=700&q=80"},
    {"name": "Venda", "language": "Tshivenḓa", "region": "South Africa", "image": "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=700&q=80"},
    {"name": "Swati", "language": "siSwati", "region": "Eswatini · South Africa", "image": "https://images.unsplash.com/photo-1509316785289-025f5b846b35?auto=format&fit=crop&w=700&q=80"},
    {"name": "Ndebele", "language": "isiNdebele", "region": "Southern Africa", "image": "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?auto=format&fit=crop&w=700&q=80"},
    {"name": "Afrikaner", "language": "Afrikaans", "region": "Southern Africa", "image": "https://images.unsplash.com/photo-1484318571209-661cf29a69c3?auto=format&fit=crop&w=700&q=80"},
    {"name": "Swahili", "language": "Kiswahili", "region": "East Africa", "image": "https://images.unsplash.com/photo-1523805009345-7448845a9e53?auto=format&fit=crop&w=700&q=80"},
]

QUESTIONS = [
    {"prompt": "Which language family includes many languages spoken across southern Africa?", "options": ["Romance", "Bantu", "Celtic", "Slavic"], "answer": 1, "note": "Many languages across central, eastern, and southern Africa belong to the Bantu language family."},
    {"prompt": "What is the name for a traditional African community gathering place often centered around a homestead?", "options": ["Agora", "Forum", "Kraal", "Piazza"], "answer": 2, "note": "A kraal is an enclosure or homestead settlement, a term used in parts of southern Africa."},
    {"prompt": "Which instrument is commonly used to carry rhythms and stories across generations?", "options": ["Bagpipe", "Harpsichord", "Accordion", "Talking drum"], "answer": 3, "note": "Drums have many roles across African musical traditions, including communication and ceremony."},
    {"prompt": "What is oral tradition?", "options": ["A written census", "Passing knowledge through spoken stories", "A style of weaving", "A harvest festival"], "answer": 1, "note": "Oral tradition keeps history, values, and knowledge alive through spoken forms."},
    {"prompt": "The Swahili language developed along which coast?", "options": ["West African coast", "Mediterranean coast", "East African coast", "Atlantic coast of Europe"], "answer": 2, "note": "Swahili grew through centuries of exchange along the East African coast."},
    {"prompt": "Which material is widely used in traditional beadwork across southern Africa?", "options": ["Glass beads", "Rubber tiles", "Tin foil", "Concrete"], "answer": 0, "note": "Colorful glass beads are used in many communities for adornment and visual expression."},
    {"prompt": "What does a family name or praise name often help preserve?", "options": ["Weather forecasts", "Market prices", "Road directions", "Ancestry and identity"], "answer": 3, "note": "Names and praise poetry can carry lineage, identity, and family history."},
    {"prompt": "Which country is home to the Basotho people and is entirely surrounded by South Africa?", "options": ["Ghana", "Lesotho", "Kenya", "Tunisia"], "answer": 1, "note": "Lesotho is a highland kingdom completely enclosed by South Africa."},
    {"prompt": "What is a common purpose of ceremonial dance?", "options": ["Measuring distance", "Keeping written records", "Celebration, storytelling, and community", "Predicting tides"], "answer": 2, "note": "Dance can mark important events and express shared histories and beliefs."},
    {"prompt": "Which principle is often described by the Nguni word Ubuntu?", "options": ["Strength through solitude", "Trade by sea", "A type of harvest", "Humanity through our relationships"], "answer": 3, "note": "Ubuntu is commonly expressed as the idea that our humanity is bound up with one another."},
]


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cultures (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                language TEXT NOT NULL,
                region TEXT NOT NULL,
                image TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY,
                prompt TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                note TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                culture_id INTEGER NOT NULL REFERENCES cultures(id),
                score INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                question_count INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS attempt_answers (
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES questions(id),
                selected_index INTEGER NOT NULL,
                is_correct INTEGER NOT NULL,
                PRIMARY KEY (attempt_id, question_id)
            );
            """
        )
        if connection.execute("SELECT COUNT(*) FROM cultures").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO cultures (name, language, region, image) VALUES (?, ?, ?, ?)",
                [(item["name"], item["language"], item["region"], item["image"]) for item in CULTURES],
            )
        if connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO questions (prompt, options_json, correct_index, note) VALUES (?, ?, ?, ?)",
                [(item["prompt"], json.dumps(item["options"]), item["answer"], item["note"]) for item in QUESTIONS],
            )


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
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return user_id


def public_user(user_id: int) -> dict:
    with database() as connection:
        row = connection.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return dict(row)


def issue_session(user_id: int, response: Response) -> None:
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
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class StartAttemptRequest(BaseModel):
    culture_id: int = Field(gt=0)


class AnswerRequest(BaseModel):
    question_id: int = Field(gt=0)
    selected_index: int = Field(ge=0, le=3)


app = FastAPI(title="Tribe Quiz API")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/quiz")
def get_quiz() -> dict:
    with database() as connection:
        cultures = [dict(row) for row in connection.execute("SELECT * FROM cultures ORDER BY id")]
        questions = [dict(row) for row in connection.execute("SELECT id, prompt, options_json, note FROM questions ORDER BY id")]
    for question in questions:
        question["options"] = json.loads(question.pop("options_json"))
    return {"cultures": cultures, "questions": questions}


@app.post("/api/auth/signup", status_code=201)
def signup(payload: SignupRequest, response: Response) -> dict:
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Add a display name to create your account.")
    try:
        with database() as connection:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, hash_password(payload.password), datetime.now(timezone.utc).isoformat()),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="An account with that email already exists.") from error
    issue_session(user_id, response)
    return {"user": public_user(user_id)}


@app.post("/api/auth/signin")
def signin(payload: LoginRequest, response: Response) -> dict:
    email = payload.email.strip().lower()
    with database() as connection:
        user = connection.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not password_matches(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    issue_session(user["id"], response)
    return {"user": public_user(user["id"])}


@app.get("/api/auth/me")
def get_current_user(tribe_quiz_session: str | None = Cookie(default=None)) -> dict:
    return {"user": public_user(require_user(tribe_quiz_session))}


@app.post("/api/auth/signout")
def signout(response: Response, tribe_quiz_session: str | None = Cookie(default=None)) -> dict:
    if tribe_quiz_session:
        token_hash = hashlib.sha256(tribe_quiz_session.encode()).hexdigest()
        with database() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return {"status": "ok"}


@app.post("/api/attempts", status_code=201)
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


@app.post("/api/attempts/{attempt_id}/answers")
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


@app.get("/api/auth/attempts")
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


initialize_database()
app.mount("/", StaticFiles(directory=FRONTEND_PATH, html=True), name="frontend")