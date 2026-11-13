import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "backend" / "tribe_quiz.db"))

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
