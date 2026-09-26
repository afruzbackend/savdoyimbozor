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
    # Xodim uzoq faol bo'lmasa — tizimdan chiqariladi (sotuvchiga emas):
    "apps.core.middleware.IdleTimeoutMiddleware",
    # Foydalanuvchi ROLIga qarab ROOT_URLCONF tanlaydi (bitta host):
    "apps.core.middleware.HostRoutingMiddleware",
    # Birinchi kirishda / tiklangan parolni almashtirish majburiy:
    "apps.core.middleware.ForcePasswordChangeMiddleware",
    # Admin/tekshiruvchi/prokuror — ikki bosqichli himoya majburiy bo'lsa, avval yoqsin:
    "apps.core.middleware.ForceTwoFactorMiddleware",
    # Prokuror (kuzatuvchi) — faqat ko'rish, har qanday o'zgartirish bloklanadi:
    "apps.core.middleware.ReadOnlyRoleMiddleware",
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
# Qayta ishlatilayotgan ulanish uzilgan bo'lsa (PostgreSQL qayta ishga tushgan) — so'rov yiqilmasin
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

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
# Prod (nginx): media'ni Django ruxsat tekshirib, nginx ichki location orqali beradi
MEDIA_X_ACCEL = env.bool("MEDIA_X_ACCEL", default=False)
# Yuklash chegarasi (fotolar 10 MB gacha — apps.core.media)
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
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
# Kesh: prod'da Redis (bir necha gunicorn worker'da UMUMIY — sozlamalar keshi, suiiste'mol
# cheklovlari). Bo'sh bo'lsa — jarayon ichidagi LocMem (dev).
CACHE_URL = env("CACHE_URL", default="")
if CACHE_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                          "LOCATION": CACHE_URL}}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/1")
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER")  # dev'da Redis yo'q bo'lsa True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE

# --- Xavfsizlik chegaralari (SystemSettings'da ham bor, bu default) ---
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15

# Admin/tekshiruvchi/prokuror shuncha daqiqa faol bo'lmasa tizimdan chiqadi (0 — o'chiq)
STAFF_IDLE_MINUTES = env.int("STAFF_IDLE_MINUTES", default=120)

# IP bo'yicha login cheklovi (apps.accounts.throttle): 15 daqiqada shuncha xato → IP bloklanadi
LOGIN_IP_MAX_FAILS = env.int("LOGIN_IP_MAX_FAILS", default=20)
LOGIN_IP_BLOCK_MINUTES = env.int("LOGIN_IP_BLOCK_MINUTES", default=30)

# --- Kamera / AI worker parametrlari ---
# Peshtaxta oldida shu soniyadan ko'p to'xtagan odam "xaridor" deb sanaladi.
# Worker shu chegarani config orqali oladi (bozor rastasida eshik yo'q — chiziq kesish emas).
VISITOR_MIN_DWELL_SECONDS = env.int("VISITOR_MIN_DWELL_SECONDS", default=5)

# --- Zaxira nusxa (apps.core.management.commands.backup) ---
# Server bozor ICHIDA bo'lmasin: zaxira albatta tashqi joyga (BACKUP_UPLOAD_CMD) yuborilsin.
BACKUP_DIR = env("BACKUP_DIR", default=str(BASE_DIR / "backups"))
BACKUP_KEEP = env.int("BACKUP_KEEP", default=14)  # nechta oxirgi nusxa saqlanadi
PG_DUMP_BIN = env("PG_DUMP_BIN", default="pg_dump")
# Masalan: rclone copy {path} offsite:bozor-backup   ({path} — fayl yo'li)
BACKUP_UPLOAD_CMD = env("BACKUP_UPLOAD_CMD", default="")

# nginx (yoki boshqa proksi) ortida: mijoz IP'si X-Real-IP dan olinadi (apps.core.net.client_ip).
# To'g'ridan-to'g'ri ochiq bo'lsa False qoldiring — aks holda sarlavhani soxtalashtirish mumkin.
BEHIND_PROXY = env.bool("BEHIND_PROXY", default=False)

# --- Xaridorga QR chek ---
# QR ichidagi manzil xaridor telefonidan ochilishi kerak: ommaviy domen (https://bozor.soliq.uz).
# Bo'sh bo'lsa — so'rov kelgan manzil olinadi (lokal demo).
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="")
RECEIPT_REPORT_DAYS = env.int("RECEIPT_REPORT_DAYS", default=7)  # xaridor necha kun ichida yozadi

# --- SMS (xaridorga nasiya eslatmasi) — apps.core.sms ---
#   ""        — o'chiq
#   "console" — yubormaydi, jurnalga yozadi (demo/test)
#   "eskiz"   — Eskiz.uz (SMS_ESKIZ_EMAIL, SMS_ESKIZ_PASSWORD, SMS_FROM; matn shabloni
#               Eskiz kabinetida tasdiqlangan bo'lishi kerak)
#   "http"    — umumiy shlyuz: POST SMS_HTTP_URL {"phone","text"} + Bearer SMS_HTTP_TOKEN
SMS_BACKEND = env("SMS_BACKEND", default="")
SMS_FROM = env("SMS_FROM", default="4546")
SMS_ESKIZ_EMAIL = env("SMS_ESKIZ_EMAIL", default="")
SMS_ESKIZ_PASSWORD = env("SMS_ESKIZ_PASSWORD", default="")
SMS_HTTP_URL = env("SMS_HTTP_URL", default="")
SMS_HTTP_TOKEN = env("SMS_HTTP_TOKEN", default="")

# --- Soliq / onlayn kassa deklaratsiyasi (apps.cash.adapters) ---
# Aniq kontrakt Soliq qo'mitasi bilan kelishuvda belgilanadi; shu yerda faqat sozlanadi.
#   ""      — o'chiq (faqat Excel import)
#   "http"  — HTTPS JSON API (TAX_API_URL + TAX_API_TOKEN), sahifalash "next" orqali
#   "inbox" — papkaga tashlanadigan CSV/JSON fayllar (SFTP/Yagona integratsiya platformasi)
TAX_ADAPTER = env("TAX_ADAPTER", default="")
TAX_API_URL = env("TAX_API_URL", default="")
TAX_API_TOKEN = env("TAX_API_TOKEN", default="")
# Javob maydonlari → bizniki: "stir=tin,date=date,amount=total,fiscal_id=terminal_id"
TAX_API_FIELDS = env("TAX_API_FIELDS", default="")
TAX_API_AMOUNT_DIVISOR = env.int("TAX_API_AMOUNT_DIVISOR", default=1)  # tiyinda bo'lsa 100
TAX_API_TIMEOUT = env.int("TAX_API_TIMEOUT", default=30)
TAX_INBOX_DIR = env("TAX_INBOX_DIR", default=str(BASE_DIR / "tax_inbox"))
TAX_SYNC_DAYS = env.int("TAX_SYNC_DAYS", default=3)  # kechikkan tuzatishlar uchun oxirgi N kun

# --- Monitoring ---
# Xatolar: Sentry protokoli. Tavsiya — o'z serverimizdagi GlitchTip (ma'lumot chet elga chiqmaydi).
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENV = env("SENTRY_ENV", default="production")
SENTRY_TRACES = env.float("SENTRY_TRACES", default=0.0)  # unumdorlik izlari ulushi (0–1)
# /healthz/ batafsil javobi uchun (X-Health-Token sarlavhasi); bo'sh — faqat admin ko'radi
HEALTH_TOKEN = env("HEALTH_TOKEN", default="")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "apps": {"level": env("APP_LOG_LEVEL", default="INFO")},
        "django.request": {"level": "ERROR"},  # 5xx xatolar gunicorn/docker logiga
    },
}

from apps.core.monitoring import init as _init_monitoring  # noqa: E402

_init_monitoring(SENTRY_DSN, environment=SENTRY_ENV, traces=SENTRY_TRACES,
                 release=env("APP_RELEASE", default=""))

# --- Telegram ogohlantirish (ixtiyoriy) ---
# Qizil signal chiqqanda biriktirilgan inspektorga xabar. Bo'sh bo'lsa — jim o'tadi.
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")

# --- Interfeys → urlconf (ROL bo'yicha tanlanadi; bitta host) ---
HOST_URLCONF = {
    "seller": "config.urls_seller",
    "inspector": "config.urls_inspector",
    "panel": "config.urls_panel",
}
