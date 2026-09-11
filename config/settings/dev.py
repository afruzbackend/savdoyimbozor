"""Dev sozlamalari — lokal PostgreSQL, Redis ixtiyoriy."""

from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    ".localhost",  # sotuvchi.localhost, nazorat.localhost, panel.localhost
]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://sotuvchi.localhost:8000",
    "http://nazorat.localhost:8000",
    "http://panel.localhost:8000",
]

# Redis bo'lmasa fon vazifalari sinxron ishlaydi (demo uzilmaydi).
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER", default=True)  # noqa: F405

# Dev'da statik fayllar oddiy uzatiladi.
