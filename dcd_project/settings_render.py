"""Fail-closed, stateless settings for the isolated Render web service."""

import os
import re
from pathlib import Path


def _required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is missing")
    return value


SECRET_KEY = _required_env("SECRET_KEY")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError("SECRET_KEY must be a generated secret of at least 50 characters")

RENDER_HOST = _required_env("RENDER_EXTERNAL_HOSTNAME").lower().rstrip(".")
if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.onrender\.com", RENDER_HOST):
    raise RuntimeError("RENDER_EXTERNAL_HOSTNAME must be the canonical *.onrender.com hostname")

DEBUG = False
WEATHER_FREE_API_ENABLED = os.environ.get("CARGO_WEATHER_FREE_API_ENABLED", "").strip().lower() == "true"
ALLOWED_HOSTS = [RENDER_HOST]
CSRF_TRUSTED_ORIGINS = [f"https://{RENDER_HOST}"]
ROOT_URLCONF = "dcd_project.urls_render"
WSGI_APPLICATION = "dcd_project.wsgi_render.application"
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

INSTALLED_APPS = []
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "optimization.admission.ComputeRateLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "optimization" / "templates"],
    "APP_DIRS": False,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
}]

# A deny-all backend satisfies Django's setting contract without SQLite, SQL
# Server, a network database, migrations, sessions, or persistent storage.
DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
DATABASE_ROUTERS = []

DATA_UPLOAD_MAX_MEMORY_SIZE = 800 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 16
DATA_UPLOAD_MAX_NUMBER_FILES = 1
FILE_UPLOAD_MAX_MEMORY_SIZE = 300 * 1024

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SECURE_HSTS_SECONDS = 86_400
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
