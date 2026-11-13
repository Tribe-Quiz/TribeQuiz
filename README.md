# Tribe Quiz

The project is split into a browser frontend and a Python/FastAPI backend. SQLite stores quiz content, users, sessions, and quiz attempts.

## Structure

- `frontend/` contains the pages, styles, page behavior, and shared API client (`api.js`).
- `backend/` contains the FastAPI entry point (`server.py`), API routes (`api.py`), request schemas (`schemas.py`), authentication helpers (`security.py`), email delivery (`mailer.py`), and SQLite setup/seeding (`database.py`).

The browser uses the shared API client to call the `/api` endpoints served by FastAPI. The server remains the source of truth for quiz and account data; starting a quiz also checks that the question count returned by the API matches the loaded quiz.

## Run locally

Install Python 3.10 or newer, create a virtual environment, then install dependencies and start the server:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.server:app --reload
```

Open `http://127.0.0.1:8000`. The API exposes quiz data, account signup/signin/signout, email verification, password recovery, answer submission, and authenticated attempt history. SQLite data is stored in `backend/tribe_quiz.db` by default; set `DATABASE_PATH` to use another location.

Passwords are stored as salted hashes. Production deployments should use HTTPS and set `COOKIE_SECURE=true`.

## Google sign-in

1. In Google Cloud Console, create an OAuth 2.0 Client ID with application type **Web application** and configure the OAuth consent screen.
2. Add the origin where the app runs to **Authorized JavaScript origins** (for local development, `http://localhost:8000` and/or `http://127.0.0.1:8000`).
3. Set the client ID in the environment where the backend runs. In PowerShell:

   ```powershell
   $env:GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
   uvicorn backend.server:app --reload
   ```

   The client ID is public and is used by the browser; no Google client secret is needed for this credential flow. The backend verifies each Google ID token before creating or signing into the matching verified-email account, then issues the app's normal secure session cookie. Set `GOOGLE_CLIENT_ID` in the hosting provider's environment settings for deployment.

## Password reset email

Signup verification and password reset links are sent over SMTP. For a free Gmail setup, enable 2-Step Verification on the sending Google account and create an App Password; use that App Password here, not the account password. In PowerShell, set the values before starting the server:

```powershell
$env:SMTP_HOST = "smtp.gmail.com"
$env:SMTP_PORT = "465"
$env:SMTP_USERNAME = "your-sender@gmail.com"
$env:SMTP_PASSWORD = "your-16-character-app-password"
$env:SMTP_FROM = $env:SMTP_USERNAME
$env:APP_BASE_URL = "http://127.0.0.1:8000"
uvicorn backend.server:app --reload
```

Set these variables in the hosting provider for deployment and set `APP_BASE_URL` to the public HTTPS origin. Signup creates a temporary pending record; the user is inserted into `users` and signed in only after opening the verification link. Verification links expire after 24 hours. Password reset links expire after one hour. Both token types are stored as hashes and are single-use; repeated requests are briefly throttled. Configure a production transactional email provider for higher sending limits.

## Deploy on Render

Use the repository root as the service root, `pip install -r requirements.txt` as the build command, and `uvicorn backend.server:app --host 0.0.0.0 --port $PORT` as the start command. Attach a persistent disk and set `DATABASE_PATH` to a file on its mount path (for example, `/var/data/tribe_quiz.db`) or SQLite data may be lost when the service is replaced. Set `COOKIE_SECURE=true` for HTTPS deployments.