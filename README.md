# Tribe Quiz

The project is split into a browser frontend and a Python/FastAPI backend. SQLite stores quiz content, users, sessions, and quiz attempts.

## Structure

- `frontend/` contains the pages, styles, and browser-side quiz behavior.
- `backend/` contains the FastAPI server and initializes the SQLite database.

## Run locally

Install Python 3.10 or newer, create a virtual environment, then install dependencies and start the server:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.server:app --reload
```

Open `http://127.0.0.1:8000`. The API exposes quiz data, account signup/signin/signout, answer submission, and authenticated attempt history. SQLite data is stored in `backend/tribe_quiz.db` by default; set `DATABASE_PATH` to use another location.

Passwords are stored as salted hashes. Production deployments should use HTTPS and set `COOKIE_SECURE=true`.

## Deploy on Render

Use the repository root as the service root, `pip install -r requirements.txt` as the build command, and `uvicorn backend.server:app --host 0.0.0.0 --port $PORT` as the start command. Attach a persistent disk and set `DATABASE_PATH` to a file on its mount path (for example, `/var/data/tribe_quiz.db`) or SQLite data may be lost when the service is replaced. Set `COOKIE_SECURE=true` for HTTPS deployments.