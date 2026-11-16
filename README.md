# Tribe Quiz

The project is split into a browser frontend and a Python/Django backend. SQLite stores quiz content, users, sessions, and quiz attempts.

## Structure

- `frontend/` contains the pages, styles, page behavior, and shared API client (`api.js`).
- `backend/` contains the Django project (`settings.py`, `urls.py`, `wsgi.py`), API views (`views.py`), request schemas (`schemas.py`), authentication helpers (`security.py`), email delivery (`mailer.py`), and SQLite setup/seeding (`database.py`).

The browser uses the shared API client to call Django's `/api` endpoints. The server remains the source of truth for quiz and account data; starting a quiz also checks that the question count returned by the API matches the loaded quiz.

## AI-generated quiz questions

The backend can generate a 30-question pool for each culture using Gemini, validate its structured output, and cache it in SQLite for 30 days. Each round draws ten questions from that pool. Add `GEMINI_API_KEY` to `backend/.env` for local development and to the hosting provider's private environment settings for deployment; never put the key in frontend code. Without a key, the app uses the existing general quiz questions as an offline fallback.

For each generated question, the backend searches Wikimedia Commons using the culture and the question's image-search phrase, then caches the thumbnail and its source/credit/license metadata with the question. The quiz displays the photo credit and links to the Commons file page. Image lookup does not require a separate API key. AI-generated cultural content and image relevance should be reviewed before being used publicly.

## Run locally

Install Python 3.10 or newer, create a virtual environment, then install dependencies and start Django:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000`. The API is documented at `http://127.0.0.1:8000/api/health` and exposes quiz data, account signup/signin/signout, email verification, password recovery, answer submission, and authenticated attempt history. SQLite data is stored in `backend/tribe_quiz.db` by default; set `DATABASE_PATH` to use another location. Environment variables in `backend/.env` are loaded automatically.

Passwords are stored as salted hashes. Production deployments should use HTTPS and set `COOKIE_SECURE=true`.

## Google sign-in

1. In Google Cloud Console, create an OAuth 2.0 Client ID with application type **Web application** and configure the OAuth consent screen.
2. Add the origin where the app runs to **Authorized JavaScript origins** (for local development, `http://localhost:8000` and/or `http://127.0.0.1:8000`).
3. Add the client ID to `backend/.env`:

   ```powershell
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   ```

   The client ID is public and is used by the browser; no Google client secret is needed for this credential flow. The backend verifies each Google ID token before creating or signing into the matching verified-email account, then issues the app's normal secure session cookie. Set `GOOGLE_CLIENT_ID` in the hosting provider's environment settings for deployment.

## Password reset email

Signup verification and password reset links are sent over SMTP. For a free Gmail setup, enable 2-Step Verification on the sending Google account and create an App Password; use that App Password here, not the account password. Add these values to `backend/.env`:

```powershell
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your-sender@gmail.com
SMTP_PASSWORD=your-16-character-app-password
SMTP_FROM=your-sender@gmail.com
APP_BASE_URL=http://127.0.0.1:8000
GEMINI_API_KEY=your-private-gemini-api-key
```

Set these variables in the hosting provider for deployment and set `APP_BASE_URL` to the public HTTPS origin. Keep `GEMINI_API_KEY` private in the provider's environment settings. Signup creates a temporary pending record; the user is inserted into `users` and signed in only after opening the verification link. Verification links expire after 24 hours. Password reset links expire after one hour. Both token types are stored as hashes and are single-use; repeated requests are briefly throttled. Configure a production transactional email provider for higher sending limits.

## Deploy on Render

Use the repository root as the service root, `pip install -r requirements.txt` as the build command, and `waitress-serve --listen=0.0.0.0:$PORT backend.wsgi:application` as the start command. Set `ALLOWED_HOSTS` to the Render hostname, set `DJANGO_SECRET_KEY` to a private random value, and configure `APP_BASE_URL`, `COOKIE_SECURE=true`, and the email/Google variables for the deployment. Attach a persistent disk and set `DATABASE_PATH` to a file on its mount path (for example, `/var/data/tribe_quiz.db`) or SQLite data may be lost when the service is replaced.