import hashlib
import json
import os
import smtplib
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import Client, SimpleTestCase
from pydantic import ValidationError

from backend.database import database, initialize_database
from backend.question_generator import GeneratedQuestion, _commons_image
from backend.security import SESSION_COOKIE, hash_password, issue_session


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

    def _culture_question_pool(self):
        return [
            {
                "id": None,
                "category": "Culture",
                "prompt": f"Which fact is specific to the Zulu culture? {index}",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "note": "The answer explains a Zulu-specific cultural fact.",
                "image_url": None,
                "image_search_term": "Zulu culture",
                "image_credit": None,
                "image_source_url": None,
                "image_license": None,
                "image_license_url": None,
            }
            for index in range(10)
        ]

    def _start_attempt(self, question_pool=None):
        with patch(
            "backend.views.questions_for_culture",
            return_value=(
                question_pool if question_pool is not None else self._culture_question_pool(),
                "ai",
            ),
        ):
            response = self.client.post(
                "/api/attempts",
                data=json.dumps({"culture_id": self._culture_id()}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_start_attempt_requires_culture_specific_questions(self):
        response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": self._culture_id()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Tribe-specific questions for Zulu", response.json()["detail"])
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])
        with database() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],
                0,
            )

    def test_start_attempt_returns_ten_questions_without_answers(self):
        attempt = self._start_attempt()

        self.assertEqual(attempt["question_count"], 10)
        self.assertEqual(len(attempt["questions"]), 10)
        self.assertEqual(attempt["question_source"], "ai")
        self.assertNotIn("correct_index", attempt["questions"][0])
        self.assertIn("image_url", attempt["questions"][0])

    def test_start_attempt_uses_cached_culture_specific_questions_without_api_key(self):
        with database() as connection:
            question_set_id = connection.execute(
                """INSERT INTO question_sets (culture_id, source, generated_at)
                   VALUES (?, 'ai', '2000-01-01T00:00:00+00:00')""",
                (self._culture_id(),),
            ).lastrowid
            connection.executemany(
                """INSERT INTO culture_questions
                   (question_set_id, category, prompt, options_json, correct_index,
                    note, image_search_term)
                   VALUES (?, 'Culture', ?, ?, 0, ?, 'Zulu culture')""",
                [
                    (
                        question_set_id,
                        f"Which fact is specific to the Zulu culture? {index}",
                        json.dumps(["A", "B", "C", "D"]),
                        "The answer explains a Zulu-specific cultural fact.",
                    )
                    for index in range(10)
                ],
            )
        response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": self._culture_id()}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        attempt = response.json()

        self.assertEqual(attempt["question_source"], "ai")
        self.assertEqual(len(attempt["questions"]), 10)
        self.assertTrue(all("Zulu" in question["prompt"] for question in attempt["questions"]))

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
        attempt = self._start_attempt(question_pool)

        self.assertEqual(attempt["question_source"], "ai")
        question = attempt["questions"][0]
        self.assertEqual(question["image_url"], "https://thumb.wikimedia.org/question.jpg")
        self.assertEqual(question["image_credit"], "Zulu beadwork.jpg — A. Artist")
        self.assertEqual(question["image_license"], "CC BY-SA 4.0")

    def test_signup_signin_and_complete_quiz_flow(self):
        verification_urls = []
        with (
            patch("backend.views.is_mail_configured", return_value=True),
            patch(
                "backend.views.send_account_verification_email",
                side_effect=lambda _email, url: verification_urls.append(url),
            ),
        ):
            signup = self.client.post(
                "/api/auth/signup",
                data=json.dumps(
                    {
                        "name": "New Player",
                        "email": "new-player@example.com",
                        "password": "StrongPass123!",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(signup.status_code, 202)
        token = parse_qs(urlparse(verification_urls[0]).query)["token"][0]
        verification = self.client.post(
            "/api/auth/verify-email",
            data=json.dumps({"token": token}),
            content_type="application/json",
        )
        self.assertEqual(verification.status_code, 200)

        signin = self.client.post(
            "/api/auth/signin",
            data=json.dumps(
                {"email": "new-player@example.com", "password": "StrongPass123!"}
            ),
            content_type="application/json",
        )
        self.assertEqual(signin.status_code, 200)
        self.assertEqual(signin.json()["user"]["name"], "New Player")

        attempt = self._start_attempt()
        last_answer = None
        for question in attempt["questions"]:
            last_answer = self.client.post(
                f"/api/attempts/{attempt['attempt_id']}/answers",
                data=json.dumps(
                    {"question_id": question["id"], "selected_index": 0}
                ),
                content_type="application/json",
            )
            self.assertEqual(last_answer.status_code, 200)

        self.assertTrue(last_answer.json()["completed"])
        self.assertEqual(last_answer.json()["answered_count"], 10)

    def test_password_reset_email_changes_password_once_and_invalidates_sessions(self):
        old_password = "OldPassword123!"
        new_password = "NewPassword456!"
        with database() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = 1",
                (hash_password(old_password),),
            )

        reset_urls = []
        with (
            patch("backend.views.is_mail_configured", return_value=True),
            patch(
                "backend.views.send_password_reset_email",
                side_effect=lambda _email, url: reset_urls.append(url),
            ),
        ):
            request = self.client.post(
                "/api/auth/forgot-password",
                data=json.dumps({"email": "player@example.com"}),
                content_type="application/json",
            )

        self.assertEqual(request.status_code, 200)
        token = parse_qs(urlparse(reset_urls[0]).query)["token"][0]
        with database() as connection:
            stored_token = connection.execute(
                "SELECT token_hash FROM password_reset_tokens WHERE user_id = 1"
            ).fetchone()
            self.assertEqual(
                stored_token["token_hash"],
                hashlib.sha256(token.encode()).hexdigest(),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id = 1"
                ).fetchone()[0],
                1,
            )

        reset = self.client.post(
            "/api/auth/reset-password",
            data=json.dumps({"token": token, "password": new_password}),
            content_type="application/json",
        )

        self.assertEqual(reset.status_code, 200)
        replay = self.client.post(
            "/api/auth/reset-password",
            data=json.dumps({"token": token, "password": new_password}),
            content_type="application/json",
        )
        self.assertEqual(replay.status_code, 400)
        with database() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM password_reset_tokens WHERE user_id = 1"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id = 1"
                ).fetchone()[0],
                0,
            )

        signin = self.client.post(
            "/api/auth/signin",
            data=json.dumps({"email": "player@example.com", "password": new_password}),
            content_type="application/json",
        )
        self.assertEqual(signin.status_code, 200)
        self.assertEqual(signin.json()["user"]["email"], "player@example.com")

    def test_password_reset_is_generic_for_unknown_accounts_and_mail_failures(self):
        with patch("backend.views.is_mail_configured", return_value=True):
            unknown = self.client.post(
                "/api/auth/forgot-password",
                data=json.dumps({"email": "unknown@example.com"}),
                content_type="application/json",
            )
        self.assertEqual(unknown.status_code, 200)

        with (
            patch("backend.views.is_mail_configured", return_value=True),
            patch(
                "backend.views.send_password_reset_email",
                side_effect=smtplib.SMTPException("test delivery failure"),
            ),
        ):
            with self.assertLogs("backend.views", level="ERROR"):
                failed_delivery = self.client.post(
                    "/api/auth/forgot-password",
                    data=json.dumps({"email": "player@example.com"}),
                    content_type="application/json",
                )

        self.assertEqual(failed_delivery.status_code, 200)
        self.assertEqual(failed_delivery.json(), unknown.json())
        with database() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM password_reset_tokens"
                ).fetchone()[0],
                0,
            )
