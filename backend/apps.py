import sys

from django.apps import AppConfig


class BackendConfig(AppConfig):
    name = "backend"

    def ready(self) -> None:
        if "test" in sys.argv or "pytest" in sys.modules:
            return

        from backend.database import initialize_database
        initialize_database()
