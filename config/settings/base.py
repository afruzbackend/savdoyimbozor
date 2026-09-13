"""
Umumiy sozlamalar — dev.py va prod.py buni import qiladi.

Tamoyillar:
- API-first (DRF), sessiya+CSRF auth (bir domen).
- Uch interfeys bitta backend: host-based routing (core.middleware.HostRoutingMiddleware).
- Pul = butun son (so'm). i18n boshidan (uz-lotin/uz-kirill/rus).
"""

from pathlib import Path

import environ

# apps/ paketini import yo'liga qo'shamiz (INSTALLED_APPS'da "apps.core" bo'ladi)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CELERY_TASK_ALWAYS_EAGER=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# --- Ilovalar ---
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",  # kelajakdagi mobil uchun tayyor, hozir sessiya ishlatamiz
    "django_htmx",
]
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.geo",
    "apps.catalog",
    "apps.shops",
    "apps.sales",
    "apps.cash",
    "apps.cameras",
    "apps.analytics",
    "apps.api",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Statik fayllarni Django o'zi uzatadi (DEBUG=False bo'lsa ham) — WhiteNoise:
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    # Foydalanuvchi ROLIga qarab ROOT_URLCONF tanlaydi (bitta host):
    "apps.core.middleware.HostRoutingMiddleware",
    # Muhim amallarni audit jurnaliga yozadi:
    "apps.core.middleware.AuditMiddleware",
]

# Standart urlconf (kirmagan foydalanuvchi uchun — login shu yerda). Rol routing buni almashtiradi.
ROOT_URLCONF = "config.urls_inspector"

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
                "django.template.context_processors.i18n",
                "apps.core.context_processors.ui_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Ma'lumotlar bazasi: PostgreSQL (dev'da ham) ---
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://bozor:bozor@127.0.0.1:5432/bozor",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = 60

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 6},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# --- Til va vaqt ---
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True
LANGUAGES = [
    ("uz", "O'zbekcha"),
    ("uz-cyrl", "Ўзбекча"),
    ("ru", "Русский"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Statik / media ---
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# WhiteNoise: collectstatic'siz ham finders orqali uzatadi (DEBUG=False lokal demo uchun)
WHITENOISE_USE_FINDERS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth oqimi ---
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"

# --- DRF: API-first, sessiya auth (mobil uchun token keyin) ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M",
}

# --- Celery ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/1")
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER")  # dev'da Redis yo'q bo'lsa True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE

# --- Xavfsizlik chegaralari (SystemSettings'da ham bor, bu default) ---
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15

# --- Kamera / AI worker parametrlari ---
# Peshtaxta oldida shu soniyadan ko'p to'xtagan odam "xaridor" deb sanaladi.
# Worker shu chegarani config orqali oladi (bozor rastasida eshik yo'q — chiziq kesish emas).
VISITOR_MIN_DWELL_SECONDS = env.int("VISITOR_MIN_DWELL_SECONDS", default=5)

# --- Telegram ogohlantirish (ixtiyoriy) ---
# Qizil signal chiqqanda biriktirilgan inspektorga xabar. Bo'sh bo'lsa — jim o'tadi.
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")

# --- Interfeys → urlconf (ROL bo'yicha tanlanadi; bitta host) ---
HOST_URLCONF = {
    "seller": "config.urls_seller",
    "inspector": "config.urls_inspector",
    "panel": "config.urls_panel",
}
