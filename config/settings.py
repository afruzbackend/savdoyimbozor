"""
Django sozlamalari — savdoyimbozor (bozor savdosini AI orqali nazorat qilish tizimi).

MVP: SQLite bilan darrov ishlaydi, tashqi xizmat kerak emas.
Production: pastdagi izohlarga qarab PostgreSQL + Redis + Celery yoqiladi.
"""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("SECRET_KEY", "dev-insecure-key-almashtiring-production-da")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = env("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")
CSRF_TRUSTED_ORIGINS = [
    o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Uchinchi tomon
    "rest_framework",
    "rest_framework.authtoken",
    "django_htmx",
    # Loyiha applari
    "accounts",
    "markets",
    "cameras",
    "events",
    "analytics",
    "inspections",
    "reports",
    "audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.user_role",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Ma'lumotlar bazasi ---
# MVP: SQLite. Production uchun .env ga DB_ENGINE=postgres qo'ying.
if env("DB_ENGINE") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "savdoyimbozor"),
            "USER": env("DB_USER", "postgres"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# --- Til va vaqt ---
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("uz", "O'zbekcha (lotin)"),
    ("uz-cyrl", "Ўзбекча (кирилл)"),
    ("ru", "Русский"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Statik va media ---
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# --- Telegram ogohlantirish (ixtiyoriy) ---
# Qizil signal chiqqanda inspektorga xabar yuborish uchun.
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")

# --- Tahlil parametrlari (analytics app o'qiydi) ---
# Peshtaxta oldida shu soniyadan ko'p to'xtagan odam "xaridor" deb sanaladi.
VISITOR_MIN_DWELL_SECONDS = int(env("VISITOR_MIN_DWELL_SECONDS", "5"))
# Deklaratsiya AI taxminining shu ulushidan past bo'lsa — qizil signal.
RISK_RED_THRESHOLD = float(env("RISK_RED_THRESHOLD", "0.4"))
RISK_YELLOW_THRESHOLD = float(env("RISK_YELLOW_THRESHOLD", "0.7"))
