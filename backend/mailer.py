import os
import smtplib
import ssl
from email.message import EmailMessage

import requests


SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USERNAME).strip()
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "smtp").strip().lower()
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.environ.get("EMAIL_FROM", "").strip()
RESEND_API_URL = "https://api.resend.com/emails"
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


class EmailDeliveryError(RuntimeError):
    pass


def is_configured() -> bool:
    if EMAIL_PROVIDER == "resend":
        return bool(RESEND_API_KEY and EMAIL_FROM)
    if EMAIL_PROVIDER != "smtp":
        return False
    return bool(SMTP_HOST and SMTP_PORT and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM)


def _send_email(message: EmailMessage) -> None:
    if EMAIL_PROVIDER == "resend":
        if not RESEND_API_KEY or not EMAIL_FROM:
            raise EmailDeliveryError("Resend email delivery is not configured.")
        try:
            response = requests.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": EMAIL_FROM,
                    "to": [str(message["To"])],
                    "subject": str(message["Subject"]),
                    "text": message.get_content(),
                },
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise EmailDeliveryError("Resend email delivery failed.") from error
        return

    if EMAIL_PROVIDER != "smtp":
        raise EmailDeliveryError(f"Unsupported email provider: {EMAIL_PROVIDER}")

    with smtplib.SMTP_SSL(
        SMTP_HOST,
        SMTP_PORT,
        timeout=10,
        context=ssl.create_default_context(),
    ) as server:
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Reset your Tribe Quiz password"
    message["From"] = EMAIL_FROM if EMAIL_PROVIDER == "resend" else SMTP_FROM
    message["To"] = recipient
    message.set_content(
        "We received a request to reset the password for your Tribe Quiz account.\n\n"
        f"Use this link within 1 hour to choose a new password:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    _send_email(message)


def send_account_verification_email(recipient: str, verification_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Verify your Tribe Quiz email"
    message["From"] = EMAIL_FROM if EMAIL_PROVIDER == "resend" else SMTP_FROM
    message["To"] = recipient
    message.set_content(
        "Thanks for signing up for Tribe Quiz.\n\n"
        f"Verify your email address within 24 hours to activate your account:\n{verification_url}\n\n"
        "If you did not create this account, you can ignore this email."
    )
    _send_email(message)
