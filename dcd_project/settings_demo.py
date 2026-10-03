"""Isolated settings for the synthetic cargo MVP demo.

Run with DJANGO_SETTINGS_MODULE=dcd_project.settings_demo. No project database,
database router, or file logger is loaded in this mode.
"""

from .settings import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
ROOT_URLCONF = "dcd_project.urls_demo"
DATA_UPLOAD_MAX_MEMORY_SIZE = 300 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 300 * 1024
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DATABASE_ROUTERS = []
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
