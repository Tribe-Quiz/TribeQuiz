from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import router
from backend.database import initialize_database


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_PATH = BASE_DIR / "frontend"

app = FastAPI(title="Tribe Quiz API")
app.include_router(router)
initialize_database()
app.mount("/", StaticFiles(directory=FRONTEND_PATH, html=True), name="frontend")
