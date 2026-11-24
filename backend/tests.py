import hashlib
import json
import os
import smtplib
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

import turso_serverless
from django.http import HttpResponse
from django.test import Client, SimpleTestCase
from pydantic import ValidationError

from backend import mailer
from backend.database import INTEGRITY_ERRORS, database, initialize_database
from backend.question_generator import (
    GeneratedQuestion,
    _commons_image,
    questions_for_culture,
)
from backend.security import COOKIE_SECURE, SESSION_COOKIE, hash_password, issue_session


class DatabaseConnectionTests(SimpleTestCase):
    def test_remote_connection_uses_turso_dbapi_and_compatible_rows(self):
        remote_connection = Mock()
        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "libsql://quiz.turso.io",
                "TURSO_AUTH_TOKEN": "test-token",
            },
        ):
            with patch(
                "backend.database.turso_serverless.connect",
                return_value=remote_connection,
            ) as connect:
                with database() as connection:
                    self.assertIs(connection, remote_connection)
                    self.assertIs(connection.row_factory, turso_serverless.Row)

        connect.assert_called_once_with(
            "libsql://quiz.turso.io",
            auth_token="test-token",
        )
        remote_connection.commit.assert_called_once_with()
        remote_connection.close.assert_called_once_with()
        self.assertIn(turso_serverless.IntegrityError, INTEGRITY_ERRORS)

    def test_incomplete_turso_configuration_does_not_fall_back_to_sqlite(self):
        with patch.dict(
            os.environ,
            {"TURSO_DATABASE_URL": "libsql://quiz.turso.io", "TURSO_AUTH_TOKEN": ""},
        ):
            with patch("backend.database.sqlite3.connect") as local_connect:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN",
                ):
                    with database():
                        pass

        local_connect.assert_not_called()

    def test_turso_rows_support_name_lookup_and_dict_conversion(self):
        cursor = Mock()
        cursor.description = (("id",), ("name",))
        row = turso_serverless.Row(cursor, (7, "Maya"))

        self.assertEqual(row["name"], "Maya")
        self.assertEqual(dict(row), {"id": 7, "name": "Maya"})


class ResendEmailTests(SimpleTestCase):
    def setUp(self):
        self.provider_patch = patch("backend.mailer.EMAIL_PROVIDER", "resend")
        self.api_key_patch = patch("backend.mailer.RESEND_API_KEY", "re_test_key")
        self.from_patch = patch(
            "backend.mailer.EMAIL_FROM",
            "Tribe Quiz <noreply@example.com>",
        )
        self.provider_patch.start()
        self.api_key_patch.start()
        self.from_patch.start()

    def tearDown(self):
        self.from_patch.stop()
        self.api_key_patch.stop()
        self.provider_patch.stop()

    def test_resend_sends_verification_and_password_reset_emails_over_https(self):
        response = Mock()
        with patch("backend.mailer.requests.post", return_value=response) as post:
            mailer.send_account_verification_email(
                "player@example.com",
                "https://tribequiz.example/verify?token=verify-token",
            )
            mailer.send_password_reset_email(
                "player@example.com",
                "https://tribequiz.example/reset?token=reset-token",
            )

        self.assertEqual(post.call_count, 2)
        verification = post.call_args_list[0]
        self.assertEqual(
            verification.args[0],
            "https://api.resend.com/emails",
        )
        self.assertEqual(
            verification.kwargs["headers"],
            {"Authorization": "Bearer re_test_key"},
        )
        self.assertEqual(
            verification.kwargs["json"],
            {
                "from": "Tribe Quiz <noreply@example.com>",
                "to": ["player@example.com"],
                "subject": "Verify your Tribe Quiz email",
                "text": (
                    "Thanks for signing up for Tribe Quiz.\n\n"
                    "Verify your email address within 24 hours to activate your account:\n"
                    "https://tribequiz.example/verify?token=verify-token\n\n"
                    "If you did not create this account, you can ignore this email.\n"
                ),
            },
        )
        self.assertEqual(verification.kwargs["timeout"], 10)
        self.assertEqual(
            post.call_args_list[1].kwargs["json"]["subject"],
            "Reset your Tribe Quiz password",
        )
        self.assertIn(
            "https://tribequiz.example/reset?token=reset-token",
            post.call_args_list[1].kwargs["json"]["text"],
        )
        self.assertEqual(response.raise_for_status.call_count, 2)

    def test_resend_http_failures_are_reported_as_delivery_errors(self):
        response = Mock()
        response.raise_for_status.side_effect = mailer.requests.HTTPError("rejected")
        with patch("backend.mailer.requests.post", return_value=response):
            with self.assertRaises(mailer.EmailDeliveryError):
                mailer.send_account_verification_email(
                    "player@example.com",
                    "https://tribequiz.example/verify?token=verify-token",
                )

    def test_resend_requires_api_key_and_verified_sender_configuration(self):
        with patch("backend.mailer.RESEND_API_KEY", ""):
            self.assertFalse(mailer.is_configured())
        with patch("backend.mailer.EMAIL_FROM", ""):
            self.assertFalse(mailer.is_configured())


class EmailJSTests(SimpleTestCase):
    def setUp(self):
        self.provider_patch = patch("backend.mailer.EMAIL_PROVIDER", "emailjs")
        self.service_patch = patch(
            "backend.mailer.EMAILJS_SERVICE_ID",
            "service-test",
        )
        self.verification_template_patch = patch(
            "backend.mailer.EMAILJS_VERIFICATION_TEMPLATE_ID",
            "template-verification",
        )
        self.reset_template_patch = patch(
            "backend.mailer.EMAILJS_RESET_TEMPLATE_ID",
            "template-reset",
        )
        self.public_key_patch = patch(
            "backend.mailer.EMAILJS_PUBLIC_KEY",
            "public-key",
        )
        self.private_key_patch = patch(
            "backend.mailer.EMAILJS_PRIVATE_KEY",
            "private-key",
        )
        self.provider_patch.start()
        self.service_patch.start()
        self.verification_template_patch.start()
        self.reset_template_patch.start()
        self.public_key_patch.start()
        self.private_key_patch.start()

    def tearDown(self):
        self.private_key_patch.stop()
        self.public_key_patch.stop()
        self.reset_template_patch.stop()
        self.verification_template_patch.stop()
        self.service_patch.stop()
        self.provider_patch.stop()

    def test_emailjs_sends_verification_and_password_reset_templates(self):
        response = Mock()
        with patch("backend.mailer.requests.post", return_value=response) as post:
            mailer.send_account_verification_email(
                "player@example.com",
                "https://tribequiz.example/verify?token=verify-token",
            )
            mailer.send_password_reset_email(
                "player@example.com",
                "https://tribequiz.example/reset?token=reset-token",
            )

        self.assertEqual(post.call_count, 2)
        verification = post.call_args_list[0]
        self.assertEqual(
            verification.args[0],
            "https://api.emailjs.com/api/v1.0/email/send",
        )
        self.assertEqual(
            verification.kwargs["json"],
            {
                "service_id": "service-test",
                "template_id": "template-verification",
                "user_id": "public-key",
                "accessToken": "private-key",
                "template_params": {
                    "to_email": "player@example.com",
                    "subject": "Verify your Tribe Quiz email",
                    "verification_url": "https://tribequiz.example/verify?token=verify-token",
                    "message_body": (
                        "Thanks for signing up for Tribe Quiz.\n\n"
                        "Verify your email address within 24 hours to activate your account:\n"
                        "https://tribequiz.example/verify?token=verify-token\n\n"
                        "If you did not create this account, you can ignore this email.\n"
                    ),
                },
            },
        )
        self.assertIn(
            "https://tribequiz.example/reset?token=reset-token",
            post.call_args_list[1].kwargs["json"]["template_params"]["message_body"],
        )
        self.assertEqual(
            post.call_args_list[1].kwargs["json"]["template_params"]["reset_url"],
            "https://tribequiz.example/reset?token=reset-token",
        )
        self.assertEqual(response.raise_for_status.call_count, 2)

    def test_emailjs_http_failures_are_reported_as_delivery_errors(self):
        response = Mock()
        response.status_code = 400
        response.text = "Invalid EmailJS template ID"
        response.raise_for_status.side_effect = mailer.requests.HTTPError(
            "rejected",
            response=response,
        )
        with patch(
            "backend.mailer.requests.post",
            return_value=response,
        ):
            with self.assertRaisesRegex(
                mailer.EmailDeliveryError,
                "HTTP 400.*Invalid EmailJS template ID",
            ):
                mailer.send_account_verification_email(
                    "player@example.com",
                    "https://tribequiz.example/verify?token=verify-token",
                )

    def test_emailjs_requires_all_service_and_template_settings(self):
        with patch("backend.mailer.EMAILJS_PRIVATE_KEY", ""):
            self.assertFalse(mailer.is_configured())


class QuizAPIAndQuestionValidationTests(SimpleTestCase):
    def setUp(self):
        self.turso_environment_patch = patch.dict(
            os.environ,
            {"TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""},
        )
        self.turso_environment_patch.start()
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
        self.turso_environment_patch.stop()

    def test_signout_invalidates_session_and_clears_cookie(self):
        response = self.client.post("/api/auth/signout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        session_cookie = response.cookies[SESSION_COOKIE]
        self.assertEqual(session_cookie["max-age"], 0)
        self.assertTrue(session_cookie["httponly"])
        self.assertEqual(bool(session_cookie["secure"]), COOKIE_SECURE)
        self.assertEqual(session_cookie["samesite"], "Lax")
        with database() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                0,
            )

        current_user = self.client.get("/api/auth/me")
        self.assertEqual(current_user.status_code, 401)

    def _culture_id(self):
        with database() as connection:
            row = connection.execute(
                "SELECT id FROM cultures WHERE name = 'Zulu'"
            ).fetchone()
        return row["id"]

    def test_leaderboard_ranks_players_by_combined_completed_quiz_scores(self):
        with database() as connection:
            culture_ids = {
                row["name"]: row["id"]
                for row in connection.execute("SELECT id, name FROM cultures")
            }
            connection.executemany(
                """INSERT INTO users (id, name, email, password_hash, created_at)
                   VALUES (?, ?, ?, 'unused', '2026-01-01')""",
                [
                    (2, "Higher Single Score", "higher@example.com"),
                    (3, "Second Overall", "second@example.com"),
                    (4, "New Registered Player", "new@example.com"),
                ],
            )
            connection.executemany(
                """INSERT INTO attempts
                   (id, user_id, culture_id, score, correct_count, question_count,
                    started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, 10, '2026-01-01', '2026-01-01')""",
                [
                    ("player-one-zulu", 1, culture_ids["Zulu"], 70, 7),
                    ("player-one-xhosa", 1, culture_ids["Xhosa"], 70, 7),
                    ("player-two-zulu", 2, culture_ids["Zulu"], 100, 10),
                    ("player-three-zulu", 3, culture_ids["Zulu"], 90, 9),
                ],
            )

        response = self.client.get("/api/leaderboard")

        self.assertEqual(response.status_code, 200)
        leaderboard = response.json()
        self.assertEqual(leaderboard["current_rank"], 1)
        self.assertEqual(leaderboard["player_count"], 4)
        self.assertEqual(
            [
                (entry["user_name"], entry["score"], entry["rank"])
                for entry in leaderboard["scores"]
            ],
            [
                ("Quiz Player", 140, 1),
                ("Higher Single Score", 100, 2),
                ("Second Overall", 90, 3),
                ("New Registered Player", 0, 4),
            ],
        )
        new_player = leaderboard["scores"][-1]
        self.assertEqual(new_player["quizzes_played"], 0)
        self.assertEqual(new_player["question_count"], 0)
        self.assertTrue(leaderboard["is_signed_in"])

    def test_leaderboard_is_available_without_signin(self):
        self.client.cookies.pop(SESSION_COOKIE, None)

        response = self.client.get("/api/leaderboard")

        self.assertEqual(response.status_code, 200)
        leaderboard = response.json()
        self.assertFalse(leaderboard["is_signed_in"])
        self.assertIsNone(leaderboard["current_rank"])
        self.assertTrue(
            all(not entry["is_current_user"] for entry in leaderboard["scores"])
        )

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
        with patch(
            "backend.views.questions_for_culture",
            return_value=([], "unavailable"),
        ):
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

    def test_static_question_pools_are_available_for_every_culture_without_ai(self):
        with database() as connection:
            cultures = [
                dict(row)
                for row in connection.execute(
                    "SELECT id, name, subregion FROM cultures ORDER BY id"
                )
            ]

        self.assertEqual(len(cultures), 20)
        north_african_cultures = [
            culture["name"]
            for culture in cultures
            if culture["subregion"] == "North Africa"
        ]
        self.assertEqual(
            north_african_cultures,
            ["Amazigh", "Beja", "Tuareg", "Sahrawi", "Kabyle"],
        )
        east_african_cultures = [
            culture["name"]
            for culture in cultures
            if culture["subregion"] == "East Africa"
        ]
        self.assertEqual(
            east_african_cultures,
            ["Swahili"],
        )
        for culture in cultures:
            with self.subTest(culture=culture["name"]):
                self.assertIn(
                    culture["subregion"],
                    {
                        "North Africa",
                        "Central Africa",
                        "East Africa",
                        "West Africa",
                        "Southern Africa",
                    },
                )
                questions, source = questions_for_culture(culture)
                self.assertEqual(source, "static")
                self.assertGreaterEqual(len(questions), 10)
                self.assertTrue(all(len(question["options"]) == 4 for question in questions))
                self.assertTrue(
                    all(0 <= question["correct_index"] < 4 for question in questions)
                )

    def test_bemba_quiz_uses_its_static_multiple_choice_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        bemba = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Bemba"
        )
        self.assertEqual(bemba["language"], "Ichibemba")
        self.assertEqual(bemba["region"], "Zambia")

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": bemba["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(attempt["question_count"], 10)
        self.assertEqual(len(attempt["questions"]), 10)

        bemba_questions = {
            question["prompt"]
            for question in questions_for_culture(bemba)[0]
        }
        self.assertTrue(
            all(
                question["prompt"] in bemba_questions
                for question in attempt["questions"]
            )
        )

    def test_lozi_quiz_uses_its_static_multiple_choice_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        lozi = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Lozi"
        )
        self.assertEqual(lozi["language"], "Silozi")
        self.assertEqual(lozi["region"], "Zambia")
        self.assertEqual(lozi["image"], "/TribeProfile/loziCover.jpg")
        cover_response = self.client.get(lozi["image"])
        self.assertEqual(cover_response.status_code, 200)
        self.assertEqual(cover_response["Content-Type"], "image/jpeg")

        lozi_questions, source = questions_for_culture(lozi)
        self.assertEqual(source, "static")
        for index, question in enumerate(lozi_questions, start=1):
            expected_url = f"/quiz-images/lozi-photos/lozi-q{index}.jpg"
            self.assertEqual(question["image_url"], expected_url)
            image_response = self.client.get(expected_url)
            self.assertEqual(image_response.status_code, 200)
            self.assertEqual(image_response["Content-Type"], "image/jpeg")

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": lozi["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(attempt["question_count"], 10)
        self.assertEqual(len(attempt["questions"]), 10)

        lozi_questions = {
            question["prompt"]
            for question in questions_for_culture(lozi)[0]
        }
        self.assertTrue(
            all(
                question["prompt"] in lozi_questions
                for question in attempt["questions"]
            )
        )

    def test_herero_quiz_uses_its_static_multiple_choice_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        herero = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Herero"
        )
        self.assertEqual(herero["language"], "Otjiherero")
        self.assertEqual(herero["region"], "Namibia · Botswana · Angola")

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": herero["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(attempt["question_count"], 10)
        self.assertEqual(len(attempt["questions"]), 10)

        herero_questions = {
            question["prompt"]
            for question in questions_for_culture(herero)[0]
        }
        self.assertTrue(
            all(
                question["prompt"] in herero_questions
                for question in attempt["questions"]
            )
        )

    def test_database_initialization_adds_missing_cultures_to_existing_database(self):
        with database() as connection:
            connection.execute(
                "DELETE FROM cultures WHERE name IN "
                "('Bemba', 'Lozi', 'Herero', 'Amazigh', 'Beja', 'Tuareg', "
                "'Sahrawi', 'Kabyle')"
            )

        initialize_database()

        with database() as connection:
            cultures = {
                row["name"]: dict(row)
                for row in connection.execute(
                    "SELECT name, language, region, image, subregion FROM cultures "
                    "WHERE name IN "
                    "('Bemba', 'Lozi', 'Herero', 'Amazigh', 'Beja', 'Tuareg', "
                    "'Sahrawi', 'Kabyle')"
                )
            }
        self.assertEqual(cultures["Bemba"]["language"], "Ichibemba")
        self.assertEqual(cultures["Lozi"]["language"], "Silozi")
        self.assertEqual(cultures["Lozi"]["region"], "Zambia")
        self.assertEqual(cultures["Herero"]["language"], "Otjiherero")
        self.assertEqual(cultures["Herero"]["region"], "Namibia · Botswana · Angola")
        self.assertEqual(cultures["Amazigh"]["language"], "Tamazight")
        self.assertEqual(cultures["Amazigh"]["subregion"], "North Africa")
        self.assertEqual(cultures["Beja"]["language"], "Beja")
        self.assertEqual(cultures["Beja"]["subregion"], "North Africa")
        self.assertEqual(cultures["Tuareg"]["language"], "Tuareg languages")
        self.assertEqual(cultures["Tuareg"]["subregion"], "North Africa")
        self.assertEqual(cultures["Sahrawi"]["language"], "Hassaniya Arabic")
        self.assertEqual(cultures["Sahrawi"]["subregion"], "North Africa")
        self.assertEqual(cultures["Kabyle"]["language"], "Kabyle Amazigh")
        self.assertEqual(cultures["Kabyle"]["subregion"], "North Africa")

    def test_quiz_api_includes_khoi_with_uploaded_cover(self):
        response = self.client.get("/api/quiz")

        self.assertEqual(response.status_code, 200)
        khoi = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Khoi"
        )
        self.assertEqual(khoi["image"], "/TribeProfile/khoi.jpg")

    def test_amazigh_quiz_is_listed_in_north_africa_and_uses_static_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        amazigh = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Amazigh"
        )
        self.assertEqual(amazigh["language"], "Tamazight")
        self.assertEqual(amazigh["region"], "Morocco · Algeria")
        self.assertEqual(amazigh["subregion"], "North Africa")

        questions, source = questions_for_culture(amazigh)
        self.assertEqual(source, "static")
        self.assertEqual(len(questions), 10)
        self.assertTrue(all(len(question["options"]) == 4 for question in questions))
        self.assertTrue(
            all(0 <= question["correct_index"] < 4 for question in questions)
        )

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": amazigh["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(len(attempt["questions"]), 10)
        self.assertTrue(
            all(question["prompt"] in {item["prompt"] for item in questions}
                for question in attempt["questions"])
        )

    def test_beja_quiz_is_listed_in_north_africa_and_uses_static_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        beja = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Beja"
        )
        self.assertEqual(beja["language"], "Beja")
        self.assertEqual(beja["region"], "Egypt · Sudan · Eritrea")
        self.assertEqual(beja["subregion"], "North Africa")

        questions, source = questions_for_culture(beja)
        self.assertEqual(source, "static")
        self.assertEqual(len(questions), 10)
        self.assertTrue(
            all(
                len(question["options"]) == 4
                and 0 <= question["correct_index"] < 4
                for question in questions
            )
        )

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": beja["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(len(attempt["questions"]), 10)

    def test_tuareg_quiz_is_listed_in_north_africa_and_uses_static_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        tuareg = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Tuareg"
        )
        self.assertEqual(tuareg["language"], "Tuareg languages")
        self.assertEqual(tuareg["region"], "Sahara · North and West Africa")
        self.assertEqual(tuareg["subregion"], "North Africa")

        questions, source = questions_for_culture(tuareg)
        self.assertEqual(source, "static")
        self.assertEqual(len(questions), 10)
        self.assertTrue(
            all(
                len(question["options"]) == 4
                and 0 <= question["correct_index"] < 4
                for question in questions
            )
        )

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": tuareg["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(len(attempt["questions"]), 10)

    def test_sahrawi_quiz_is_listed_in_north_africa_and_uses_static_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        sahrawi = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Sahrawi"
        )
        self.assertEqual(sahrawi["language"], "Hassaniya Arabic")
        self.assertEqual(sahrawi["region"], "Western Sahara")
        self.assertEqual(sahrawi["subregion"], "North Africa")

        questions, source = questions_for_culture(sahrawi)
        self.assertEqual(source, "static")
        self.assertEqual(len(questions), 10)
        self.assertTrue(
            all(
                len(question["options"]) == 4
                and 0 <= question["correct_index"] < 4
                for question in questions
            )
        )

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": sahrawi["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(len(attempt["questions"]), 10)

    def test_kabyle_quiz_is_listed_in_north_africa_and_uses_static_questions(self):
        response = self.client.get("/api/quiz")
        self.assertEqual(response.status_code, 200)
        kabyle = next(
            culture
            for culture in response.json()["cultures"]
            if culture["name"] == "Kabyle"
        )
        self.assertEqual(kabyle["language"], "Kabyle Amazigh")
        self.assertEqual(kabyle["region"], "Kabylia · Algeria")
        self.assertEqual(kabyle["subregion"], "North Africa")

        questions, source = questions_for_culture(kabyle)
        self.assertEqual(source, "static")
        self.assertEqual(len(questions), 10)
        self.assertTrue(
            all(
                len(question["options"]) == 4
                and 0 <= question["correct_index"] < 4
                for question in questions
            )
        )

        attempt_response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": kabyle["id"]}),
            content_type="application/json",
        )
        self.assertEqual(attempt_response.status_code, 201)
        attempt = attempt_response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(len(attempt["questions"]), 10)

    def test_khoi_question_images_match_question_numbers_and_are_served(self):
        with database() as connection:
            culture = dict(
                connection.execute(
                    "SELECT id, name FROM cultures WHERE name = 'Khoi'"
                ).fetchone()
            )

        questions, source = questions_for_culture(culture)

        self.assertEqual(source, "static")
        self.assertEqual(len(questions), 10)
        for index, question in enumerate(questions, start=1):
            extension = "webp" if index == 7 else "jpg"
            expected_url = f"/quiz-images/khoi-photos/khoi-q{index}.{extension}"
            self.assertEqual(question["image_url"], expected_url)
            response = self.client.get(expected_url)
            self.assertEqual(response.status_code, 200)
            expected_type = "image/webp" if extension == "webp" else "image/jpeg"
            self.assertEqual(response["Content-Type"], expected_type)

    def test_start_attempt_uses_tribe_specific_static_questions_without_ai(self):
        culture_id = self._culture_id()

        response = self.client.post(
            "/api/attempts",
            data=json.dumps({"culture_id": culture_id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        attempt = response.json()
        self.assertEqual(attempt["question_source"], "static")
        self.assertEqual(attempt["question_count"], 10)
        self.assertEqual(len(attempt["questions"]), 10)
        static_prompts = {
            question["prompt"]
            for question in questions_for_culture(
                {"id": culture_id, "name": "Zulu"}
            )[0]
        }
        self.assertTrue(
            all(
                question["prompt"] in static_prompts
                for question in attempt["questions"]
            )
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
        with patch("backend.question_generator._static_questions", return_value=[]):
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

    def test_incomplete_attempt_can_be_resumed_with_saved_progress(self):
        attempt = self._start_attempt()
        response = self.client.post(
            f"/api/attempts/{attempt['attempt_id']}/answers",
            data=json.dumps(
                {
                    "question_id": attempt["questions"][0]["id"],
                    "selected_index": 0,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        resumed = self.client.get(f"/api/attempts/{attempt['attempt_id']}")

        self.assertEqual(resumed.status_code, 200)
        payload = resumed.json()
        self.assertEqual(payload["answered_count"], 1)
        self.assertEqual(payload["score"], 10)
        self.assertEqual(payload["answers"][0]["selected_index"], 0)
        self.assertEqual(payload["answers"][0]["correct_index"], 0)
        self.assertNotIn("correct_index", payload["questions"][0])
        self.assertNotIn("correct_index", payload["questions"][1])

    def test_attempt_cannot_be_resumed_by_another_user(self):
        attempt = self._start_attempt()
        with database() as connection:
            connection.execute(
                """INSERT INTO users (id, name, email, password_hash, created_at)
                   VALUES (2, 'Another Player', 'another@example.com', 'unused', '2026-01-01')"""
            )
        other_client = Client()
        response = HttpResponse()
        issue_session(2, response)
        other_client.cookies[SESSION_COOKIE] = response.cookies[SESSION_COOKIE].value

        response = other_client.get(f"/api/attempts/{attempt['attempt_id']}")

        self.assertEqual(response.status_code, 404)

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

        amazigh_response = self.client.get("/TribeProfile/amazigh.svg")
        self.assertEqual(amazigh_response.status_code, 200)
        self.assertEqual(amazigh_response["Content-Type"], "image/svg+xml")

        beja_response = self.client.get("/TribeProfile/beja.svg")
        self.assertEqual(beja_response.status_code, 200)
        self.assertEqual(beja_response["Content-Type"], "image/svg+xml")

        tuareg_response = self.client.get("/TribeProfile/tuareg.svg")
        self.assertEqual(tuareg_response.status_code, 200)
        self.assertEqual(tuareg_response["Content-Type"], "image/svg+xml")

        sahrawi_response = self.client.get("/TribeProfile/sahrawi.svg")
        self.assertEqual(sahrawi_response.status_code, 200)
        self.assertEqual(sahrawi_response["Content-Type"], "image/svg+xml")

        kabyle_response = self.client.get("/TribeProfile/kabyle.svg")
        self.assertEqual(kabyle_response.status_code, 200)
        self.assertEqual(kabyle_response["Content-Type"], "image/svg+xml")

        bemba_response = self.client.get("/TribeProfile/bemba.svg")
        self.assertEqual(bemba_response.status_code, 200)
        self.assertEqual(bemba_response["Content-Type"], "image/svg+xml")

    def test_khoi_profile_image_is_served_from_the_local_project(self):
        response = self.client.get("/TribeProfile/khoi.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_database_initialization_adds_missing_khoi_to_existing_database(self):
        with database() as connection:
            connection.execute("DELETE FROM cultures WHERE name = 'Khoi'")

        initialize_database()

        with database() as connection:
            khoi_count = connection.execute(
                "SELECT COUNT(*) FROM cultures WHERE name = 'Khoi'"
            ).fetchone()[0]
        self.assertEqual(khoi_count, 1)

    def test_static_question_images_are_matched_and_served_locally(self):
        questions, source = questions_for_culture(
            {"id": self._culture_id(), "name": "Zulu"}
        )
        amasi = next(
            question
            for question in questions
            if question["prompt"] == "What is 'Amasi' in Zulu culture?"
        )

        self.assertEqual(source, "static")
        self.assertEqual(amasi["image_url"], "/quiz-images/zulu-photos/amasi.jpg")
        response = self.client.get(amasi["image_url"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_unreferenced_question_images_are_not_served(self):
        response = self.client.get("/quiz-images/zulu-photos/not-a-quiz-image.jpg")

        self.assertEqual(response.status_code, 404)

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

    def test_signup_cleans_pending_record_when_email_delivery_fails(self):
        with (
            patch("backend.views.is_mail_configured", return_value=True),
            patch(
                "backend.views.send_account_verification_email",
                side_effect=mailer.EmailDeliveryError("provider unavailable"),
            ),
        ):
            with self.assertLogs("backend.views", level="ERROR"):
                response = self.client.post(
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

        self.assertEqual(response.status_code, 503)
        with database() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM pending_signups WHERE email = ?",
                    ("new-player@example.com",),
                ).fetchone()[0],
                0,
            )

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
        self.assertIn("if an account matches", unknown.json()["message"].lower())
        self.assertNotIn("has been sent", unknown.json()["message"])

        delivery_errors = (
            smtplib.SMTPException("test SMTP delivery failure"),
            mailer.EmailDeliveryError("test HTTPS delivery failure"),
        )
        for delivery_error in delivery_errors:
            with (
                patch("backend.views.is_mail_configured", return_value=True),
                patch(
                    "backend.views.send_password_reset_email",
                    side_effect=delivery_error,
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
