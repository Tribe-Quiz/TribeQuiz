import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import Client, SimpleTestCase
from pydantic import ValidationError

from backend.database import database, initialize_database
from backend.question_generator import GeneratedQuestion, _commons_image
from backend.security import SESSION_COOKIE, issue_session


class QuizAPIAndQuestionValidationTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path_patch = patch(
            "backend.database.DATABASE_PATH",
            Path(self.temporary_directory.name) / "quiz-test.db",
        )
        self.database_path_patch.start()
        self.gemini_key_patch = patch.dict(os.environ, {"GEMINI_API_KEY": ""})
        self.gemini_key_patch.start()
        initialize_database()
        self.client = Client()
        with database() as connection:
            connection.execute(
                """INSERT INTO users (id, name, email, password_hash, created_at)
                   VALUES (1, 'Quiz Player', 'player@example.com', 'unused', '2026-01-01')"""
            )
        response = HttpResponse()
        issue_session(1, response)
        self.client.cookies[SESSION_COOKIE] = response.cookies[SESSION_COOKIE].value

    def tearDown(self):
        self.gemini_key_patch.stop()
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    def _culture_id(self):
        with database() as connection:
            row = connection.execute(
                "SELECT id FROM cultures WHERE name = 'Zulu'"
            ).fetchone()
        return row["id"]

    def _start_attempt(self):
        response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": self._culture_id()}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_start_attempt_returns_ten_questions_without_answers(self):
        attempt = self._start_attempt()

        self.assertEqual(attempt["question_count"], 10)
        self.assertEqual(len(attempt["questions"]), 10)
        self.assertEqual(attempt["question_source"], "general")
        self.assertNotIn("correct_index", attempt["questions"][0])
        self.assertIn("image_url", attempt["questions"][0])

    def test_start_attempt_requires_a_signed_in_user(self):
        self.client.cookies.pop(SESSION_COOKIE, None)

        response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": self._culture_id()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_timeout_answer_is_recorded_and_duplicate_answer_is_rejected(self):
        attempt = self._start_attempt()
        question_id = attempt["questions"][0]["id"]
        answer = {
            "question_id": question_id,
            "selected_index": -1,
        }

        response = self.client.post(
            f"/api/attempts/{attempt['attempt_id']}/answers",
            data=json.dumps(answer),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["correct"])
        self.assertEqual(response.json()["answered_count"], 1)
        duplicate = self.client.post(
            f"/api/attempts/{attempt['attempt_id']}/answers",
            data=json.dumps(answer),
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_profile_images_are_served_from_the_local_project(self):
        response = self.client.get("/TribeProfile/zulu.webp")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/webp")

    def test_generated_questions_reject_duplicate_answer_choices(self):
        with self.assertRaises(ValidationError):
            GeneratedQuestion.model_validate(
                {
                    "category": "Culture",
                    "prompt": "Which option best describes this tradition?",
                    "options": ["Same", "Same", "Other", "Another"],
                    "correct_index": 0,
                    "note": "The explanation describes the correct answer.",
                    "image_search_term": "traditional clothing",
                }
            )

    def test_commons_images_include_photo_credit_and_license(self):
        response = Mock()
        response.json.return_value = {
            "query": {
                "pages": {
                    "1": {
                        "title": "File:Zulu beadwork.jpg",
                        "imageinfo": [
                            {
                                "thumburl": "https://thumb.wikimedia.org/beadwork.jpg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Zulu_beadwork.jpg",
                                "extmetadata": {
                                    "Artist": {"value": "<a href='/wiki/User:Artist'>A. Artist</a>"},
                                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "LicenseUrl": {
                                        "value": "https://creativecommons.org/licenses/by-sa/4.0/"
                                    },
                                },
                            }
                        ],
                    }
                }
            }
        }
        with patch("backend.question_generator.requests.get", return_value=response):
            image = _commons_image("Zulu beadwork")

        self.assertEqual(image["image_url"], "https://thumb.wikimedia.org/beadwork.jpg")
        self.assertEqual(image["image_credit"], "Zulu beadwork.jpg — A. Artist")
        self.assertEqual(image["image_license"], "CC BY-SA 4.0")
        self.assertEqual(
            image["image_license_url"],
            "https://creativecommons.org/licenses/by-sa/4.0/",
        )

    def test_ai_question_photo_and_attribution_are_returned_with_attempt(self):
        question_pool = [
            {
                "id": None,
                "category": "History",
                "prompt": f"Which fact describes this Zulu history topic {index}?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "note": "The explanation describes the documented historical fact.",
                "image_url": "https://thumb.wikimedia.org/question.jpg",
                "image_search_term": "Zulu historical site",
                "image_credit": "Zulu beadwork.jpg — A. Artist",
                "image_source_url": "https://commons.wikimedia.org/wiki/File:Question.jpg",
                "image_license": "CC BY-SA 4.0",
                "image_license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            }
            for index in range(10)
        ]
        with patch("backend.views.questions_for_culture", return_value=(question_pool, "ai")):
            attempt = self._start_attempt()

        self.assertEqual(attempt["question_source"], "ai")
        question = attempt["questions"][0]
        self.assertEqual(question["image_url"], "https://thumb.wikimedia.org/question.jpg")
        self.assertEqual(question["image_credit"], "Zulu beadwork.jpg — A. Artist")
        self.assertEqual(question["image_license"], "CC BY-SA 4.0")
