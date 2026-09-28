import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("bozor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Rejalashtirilgan fon vazifalari (spec 2-bo'lim):
app.conf.beat_schedule = {
    # Monitoring: fon vazifalari tirikligi (/healthz/ → celery)
    "heartbeat": {
        "task": "apps.core.tasks.heartbeat",
        "schedule": crontab(minute="*"),
    },
    # Bugungi rostlik ballarini yangilash (standart har 5 daqiqa). Do'konlar ko'p bo'lsa (>3 000)
    # oraliqni oshiring: .env da RECOMPUTE_EVERY_MIN=15 (bitta hisob ~30 ms × do'kon soni)
    "recompute-today": {
        "task": "apps.analytics.tasks.recompute_today",
        "schedule": crontab(minute=f"*/{max(1, min(59, int(os.environ.get('RECOMPUTE_EVERY_MIN', '5'))))}"),
    },
    # Har kecha 01:00 da o'tgan kunni yakuniy hisoblash + bozor narxi
    "recompute-yesterday": {
        "task": "apps.analytics.tasks.recompute_yesterday",
        "schedule": crontab(hour=1, minute=0),
    },
    # Darvoza kamerasi ↔ kirim: kechagi tushirishlar (oxirgi oyna 14:00 da yopiladi)
    "check-gate-yesterday": {
        "task": "apps.analytics.tasks.check_gate_yesterday",
        "schedule": crontab(hour=14, minute=10),
    },
    # Har kecha 02:30 da zaxira nusxa (baza + fotolar, tashqi joyga)
    "nightly-backup": {
        "task": "apps.core.tasks.nightly_backup",
        "schedule": crontab(hour=2, minute=30),
    },
    # Soliq / onlayn kassa deklaratsiyasi (TAX_ADAPTER bo'sh bo'lsa — jim o'tadi).
    # Ertalab kechagi kun, tushda kechikkan tuzatishlar.
    "sync-declarations": {
        "task": "apps.cash.tasks.sync_declarations",
        "schedule": crontab(hour="4,13", minute=15),
    },
    # Xaridorlarga nasiya SMS eslatmasi (1 kun oldin, o'sha kuni, 3 kun o'tganda)
    "debt-sms-reminders": {
        "task": "apps.sales.tasks.debt_sms_reminders",
        "schedule": crontab(hour="10,15", minute=0),  # 15:00 — tarmoq xatosi bo'lganlar qayta
    },
    # Har kecha 03:45 da muddati o'tgan sessiyalar tozalanadi
    "clear-sessions": {
        "task": "apps.core.tasks.clear_sessions",
        "schedule": crontab(hour=3, minute=45),
    },
    # Har kuni 20:00 da sotuvchilarga kun yakuni/kassa yopishni eslatish
    "close-reminders": {
        "task": "apps.sales.tasks.close_reminders",
        "schedule": crontab(hour=20, minute=0),
    },
}
