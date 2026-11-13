from django.apps import AppConfig


class BackendConfig(AppConfig):
    name = "backend"

    def ready(self) -> None:
        from backend.database import initialize_database

        initialize_database()
