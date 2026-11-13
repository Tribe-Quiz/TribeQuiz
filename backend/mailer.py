import os
import smtplib
import ssl
from email.message import EmailMessage


SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USERNAME).strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_PORT and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM)


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Reset your Tribe Quiz password"
    message["From"] = SMTP_FROM
    message["To"] = recipient
    message.set_content(
        "We received a request to reset the password for your Tribe Quiz account.\n\n"
        f"Use this link within 1 hour to choose a new password:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    with smtplib.SMTP_SSL(
        SMTP_HOST,
        SMTP_PORT,
        timeout=10,
        context=ssl.create_default_context(),
    ) as server:
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def send_account_verification_email(recipient: str, verification_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Verify your Tribe Quiz email"
    message["From"] = SMTP_FROM
    message["To"] = recipient
    message.set_content(
        "Thanks for signing up for Tribe Quiz.\n\n"
        f"Verify your email address within 24 hours to activate your account:\n{verification_url}\n\n"
        "If you did not create this account, you can ignore this email."
    )
    with smtplib.SMTP_SSL(
        SMTP_HOST,
        SMTP_PORT,
        timeout=10,
        context=ssl.create_default_context(),
    ) as server:
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)
