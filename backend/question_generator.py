import html
import json
import logging
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Literal

import requests
from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from backend.database import QUESTIONS, database


logger = logging.getLogger(__name__)
QUESTION_COUNT = 10
QUESTION_POOL_SIZE = 30
CACHE_LIFETIME = timedelta(days=30)
GEMINI_MODEL = "gemini-4-hydrogen"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"


class GeneratedQuestion(BaseModel):
    category: Literal[
        "Language",
        "History",
        "Tradition",
        "Culture",
        "Music",
        "Geography",
        "Food",
        "Notable People",
        "Proverbs",
    ]
    prompt: str = Field(min_length=10, max_length=400)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    note: str = Field(min_length=10, max_length=500)
    image_search_term: str = Field(min_length=3, max_length=120)
    image_url: str | None = None
    image_credit: str | None = None
    image_source_url: str | None = None
    image_license: str | None = None
    image_license_url: str | None = None

    @field_validator("options")
    @classmethod
    def options_must_be_distinct(cls, options: list[str]) -> list[str]:
        if any(not option.strip() for option in options):
            raise ValueError("Answer choices cannot be blank.")
        if len({option.strip().casefold() for option in options}) != 4:
            raise ValueError("Answer choices must be distinct.")
        return options


class GeneratedQuestionSet(BaseModel):
    questions: list[GeneratedQuestion] = Field(
        min_length=QUESTION_POOL_SIZE,
        max_length=QUESTION_POOL_SIZE,
    )

    @model_validator(mode="after")
    def prompts_must_be_distinct(self) -> "GeneratedQuestionSet":
        prompts = [question.prompt.strip().casefold() for question in self.questions]
        if len(set(prompts)) != len(prompts):
            raise ValueError("Question prompts must be distinct.")
        return self


def _cached_questions(culture_id: int, *, fresh_only: bool) -> list[dict]:
    with database() as connection:
        query = """
            SELECT culture_questions.*, question_sets.source
            FROM culture_questions
            JOIN question_sets ON question_sets.id = culture_questions.question_set_id
            WHERE question_sets.culture_id = ? AND question_sets.source = 'ai'
        """
        parameters: tuple[object, ...] = (culture_id,)
        if fresh_only:
            query += " AND question_sets.generated_at > ?"
            parameters += ((datetime.now(timezone.utc) - CACHE_LIFETIME).isoformat(),)
        query += " ORDER BY question_sets.generated_at DESC, culture_questions.id"
        rows = connection.execute(query, parameters).fetchall()
    if not rows:
        return []
    latest_set_id = rows[0]["question_set_id"]
    return [
        {
            "id": row["id"],
            "category": row["category"],
            "prompt": row["prompt"],
            "options": json.loads(row["options_json"]),
            "correct_index": row["correct_index"],
            "note": row["note"],
            "image_url": row["image_url"],
            "image_search_term": row["image_search_term"],
            "image_credit": row["image_credit"],
            "image_source_url": row["image_source_url"],
            "image_license": row["image_license"],
            "image_license_url": row["image_license_url"],
        }
        for row in rows
        if row["question_set_id"] == latest_set_id
    ]


def _fallback_questions() -> list[dict]:
    return [
        {
            "id": None,
            "category": "Culture",
            "prompt": question["prompt"],
            "options": question["options"],
            "correct_index": question["answer"],
            "note": question["note"],
            "image_url": None,
            "image_search_term": question["prompt"],
            "image_credit": None,
            "image_source_url": None,
            "image_license": None,
            "image_license_url": None,
        }
        for question in QUESTIONS
    ]


def _commons_image(search_term: str) -> dict[str, str | None]:
    try:
        response = requests.get(
            COMMONS_API_URL,
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {search_term}",
                "gsrnamespace": 6,
                "gsrlimit": 1,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 900,
                "format": "json",
            },
            headers={"User-Agent": "TribeQuiz/1.0 (culture quiz image lookup)"},
            timeout=(3, 10),
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
    except (requests.RequestException, ValueError) as error:
        logger.warning("Could not find a Commons image for %r: %s", search_term, error)
        pages = {}

    for page in pages.values():
        image_info = (page.get("imageinfo") or [{}])[0]
        if not image_info.get("thumburl") or not image_info.get("descriptionurl"):
            continue
        metadata = image_info.get("extmetadata", {})
        artist = html.unescape(metadata.get("Artist", {}).get("value", ""))
        artist = re.sub(r"<[^>]*>", "", artist).strip()
        license_name = html.unescape(metadata.get("LicenseShortName", {}).get("value", ""))
        license_url = metadata.get("LicenseUrl", {}).get("value")
        title = page.get("title", "Wikimedia Commons")
        title = title.removeprefix("File:")
        credit = f"{title} — {artist}" if artist else title
        return {
            "image_url": image_info.get("thumburl"),
            "image_credit": credit,
            "image_source_url": image_info.get("descriptionurl"),
            "image_license": license_name or None,
            "image_license_url": license_url,
        }

    return {
        "image_url": None,
        "image_credit": None,
        "image_source_url": None,
        "image_license": None,
        "image_license_url": None,
    }


def _find_question_image(culture: dict, question: GeneratedQuestion) -> dict[str, str | None]:
    specific_image = _commons_image(f"{culture['name']} {question.image_search_term}")
    if specific_image["image_url"]:
        return specific_image
    return _commons_image(f"{culture['name']} people culture {culture['region']}")


def _generate_questions(culture: dict) -> list[GeneratedQuestion]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    prompt = (
        f"Create {QUESTION_POOL_SIZE} accurate, respectful multiple-choice quiz questions "
        f"about the {culture['name']} people and culture. Language: {culture['language']}. "
        f"Region: {culture['region']}. Cover the required categories across the complete set: "
        "language, history, traditions, culture, music, geography, food, and notable people. "
        "Use four distinct plausible answer choices per question and exactly one correct answer. "
        "The explanation must briefly explain the answer. Prefer well-established facts and avoid "
        "present-day office holders, uncertain claims, stereotypes, and sacred or restricted "
        "cultural practices. Questions must be specific to this culture, not generic African trivia. "
        "For each question, include a concise search phrase for a relevant illustrative photo. "
        "Use visible, concrete subjects such as places, objects, food, art, or instruments; do not "
        "use abstract concepts as photo subjects. The photo phrase is metadata only; do not return a URL."
    )
    client = genai.Client(api_key=api_key)
    response = client.interactions.create(
        model=GEMINI_MODEL,
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": GeneratedQuestionSet.model_json_schema(),
        },
        timeout=120,
    )
    output = response.output_text
    if not output:
        raise ValueError("Gemini returned an empty question set.")
    question_set = GeneratedQuestionSet.model_validate_json(output)
    with ThreadPoolExecutor(max_workers=6) as executor:
        images = list(
            executor.map(
                lambda question: _find_question_image(culture, question),
                question_set.questions,
            )
        )
    return [
        question.model_copy(update=image)
        for question, image in zip(question_set.questions, images)
    ]


def questions_for_culture(culture: dict) -> tuple[list[dict], str]:
    cached = _cached_questions(culture["id"], fresh_only=True)
    if len(cached) >= QUESTION_COUNT:
        return cached, "ai"

    if os.environ.get("GEMINI_API_KEY", "").strip():
        try:
            questions = _generate_questions(culture)
        except (genai_errors.APIError, ValidationError, ValueError) as error:
            logger.warning(
                "Could not generate questions for %s; trying cached or general questions: %s",
                culture["name"],
                error,
            )
        else:
            generated_at = datetime.now(timezone.utc).isoformat()
            with database() as connection:
                cursor = connection.execute(
                    "INSERT INTO question_sets (culture_id, source, generated_at) VALUES (?, 'ai', ?)",
                    (culture["id"], generated_at),
                )
                question_set_id = cursor.lastrowid
                connection.executemany(
                    """INSERT INTO culture_questions
                       (question_set_id, category, prompt, options_json, correct_index,
                        note, image_url, image_search_term, image_credit, image_source_url,
                        image_license, image_license_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            question_set_id,
                            question.category,
                            question.prompt,
                            json.dumps(question.options, ensure_ascii=False),
                            question.correct_index,
                            question.note,
                            question.image_url,
                            question.image_search_term,
                            question.image_credit,
                            question.image_source_url,
                            question.image_license,
                            question.image_license_url,
                        )
                        for question in questions
                    ],
                )
            return _cached_questions(culture["id"], fresh_only=True), "ai"

    cached = _cached_questions(culture["id"], fresh_only=False)
    if len(cached) >= QUESTION_COUNT:
        return cached, "ai"
    return _fallback_questions(), "general"


def select_quiz_questions(questions: list[dict]) -> list[dict]:
    if len(questions) < QUESTION_COUNT:
        raise ValueError("A quiz requires at least ten questions.")
    return random.sample(questions, QUESTION_COUNT)
