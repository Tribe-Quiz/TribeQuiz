import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import turso_serverless


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "backend" / "tribe_quiz.db"))
INTEGRITY_ERRORS = (sqlite3.IntegrityError, turso_serverless.IntegrityError)

CULTURES = [
    {"name": "Zulu", "language": "IsiZulu", "region": "South Africa", "image": "/TribeProfile/zulu.webp"},
    {"name": "Xhosa", "language": "IsiXhosa", "region": "South Africa", "image": "/TribeProfile/xhosa.webp"},
    {"name": "Sesotho", "language": "Sesotho", "region": "Lesotho · South Africa", "image": "/TribeProfile/sesotho.webp"},
    {"name": "Sepedi", "language": "Sesotho sa Leboa", "region": "South Africa", "image": "/TribeProfile/sepedi.webp"},
    {"name": "Tswana", "language": "Setswana", "region": "Botswana · South Africa", "image": "/TribeProfile/tswana.webp"},
    {"name": "Tsonga", "language": "Xitsonga", "region": "Southern Africa", "image": "/TribeProfile/tsonga.webp"},
    {"name": "Venda", "language": "Tshivenḓa", "region": "South Africa", "image": "/TribeProfile/vhenda.webp"},
    {"name": "Swati", "language": "siSwati", "region": "Eswatini · South Africa", "image": "/TribeProfile/swati.webp"},
    {"name": "Ndebele", "language": "isiNdebele", "region": "Southern Africa", "image": "/TribeProfile/ndebele.webp"},
    {"name": "Afrikaner", "language": "Afrikaans", "region": "Southern Africa", "image": "/TribeProfile/afrikaans.png"},
    {"name": "Swahili", "language": "Kiswahili", "region": "East Africa", "image": "/TribeProfile/swahili.png"},
    {"name": "Bemba", "language": "Ichibemba", "region": "Zambia", "image": "/TribeProfile/bemba.svg"},
    {"name": "Lozi", "language": "Silozi", "region": "Zambia", "image": "/TribeProfile/lozi.svg"},
    {"name": "Herero", "language": "Otjiherero", "region": "Namibia · Botswana · Angola", "image": "/TribeProfile/herero.svg"},
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
def database() -> Iterator[sqlite3.Connection | turso_serverless.Connection]:
    database_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    auth_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if bool(database_url) != bool(auth_token):
        raise RuntimeError(
            "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must both be configured."
        )
    if database_url:
        connection = turso_serverless.connect(database_url, auth_token=auth_token)
        connection.row_factory = turso_serverless.Row
    else:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DATABASE_PATH)
        connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
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
            CREATE TABLE IF NOT EXISTS question_sets (
                id INTEGER PRIMARY KEY,
                culture_id INTEGER NOT NULL REFERENCES cultures(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS question_sets_culture_date
                ON question_sets (culture_id, generated_at DESC);
            CREATE TABLE IF NOT EXISTS culture_questions (
                id INTEGER PRIMARY KEY,
                question_set_id INTEGER NOT NULL REFERENCES question_sets(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                prompt TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                note TEXT NOT NULL,
                image_url TEXT,
                image_search_term TEXT NOT NULL,
                image_credit TEXT,
                image_source_url TEXT,
                image_license TEXT,
                image_license_url TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_signups (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
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
            CREATE TABLE IF NOT EXISTS quiz_attempt_questions (
                id INTEGER PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                question_order INTEGER NOT NULL,
                culture_question_id INTEGER REFERENCES culture_questions(id) ON DELETE SET NULL,
                prompt TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                note TEXT NOT NULL,
                category TEXT NOT NULL,
                image_url TEXT,
                image_search_term TEXT NOT NULL,
                image_credit TEXT,
                image_source_url TEXT,
                image_license TEXT,
                image_license_url TEXT,
                UNIQUE (attempt_id, question_order)
            );
            CREATE TABLE IF NOT EXISTS quiz_attempt_answers (
                attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
                attempt_question_id INTEGER NOT NULL REFERENCES quiz_attempt_questions(id),
                selected_index INTEGER NOT NULL,
                is_correct INTEGER NOT NULL,
                PRIMARY KEY (attempt_id, attempt_question_id)
            );
            """
        )
        for table in ("culture_questions", "quiz_attempt_questions"):
            existing_columns = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            for column in (
                "image_credit",
                "image_source_url",
                "image_license",
                "image_license_url",
            ):
                if column not in existing_columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        connection.executemany(
            """INSERT INTO cultures (name, language, region, image)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   language = excluded.language,
                   region = excluded.region,
                   image = excluded.image""",
            [
                (item["name"], item["language"], item["region"], item["image"])
                for item in CULTURES
            ],
        )
        if connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO questions (prompt, options_json, correct_index, note) VALUES (?, ?, ?, ?)",
                [(item["prompt"], json.dumps(item["options"]), item["answer"], item["note"]) for item in QUESTIONS],
            )
