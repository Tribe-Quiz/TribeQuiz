from django.urls import path

from backend import views


urlpatterns = [
    path("api/health", views.health),
    path("api/quiz", views.get_quiz),
    path("api/auth/signup", views.signup),
    path("api/auth/verify-email", views.verify_email),
    path("api/auth/signin", views.signin),
    path("api/auth/forgot-password", views.forgot_password),
    path("api/auth/reset-password", views.reset_password),
    path("api/auth/google/config", views.google_auth_config),
    path("api/auth/google", views.google_signin),
    path("api/auth/me", views.get_current_user),
    path("api/auth/signout", views.signout),
    path("api/attempts", views.start_attempt),
    path("api/attempts/<str:attempt_id>/answers", views.submit_answer),
    path("api/auth/attempts", views.get_user_attempts),
    path("", views.serve_frontend, {"filename": "index.html"}),
    path("<str:filename>", views.serve_frontend),
]
