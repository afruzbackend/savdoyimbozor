import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("bozor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Rejalashtirilgan fon vazifalari (spec 2-bo'lim):
app.conf.beat_schedule = {
    # Har 5 daqiqada bugungi rostlik ballarini yangilash
    "recompute-today": {
        "task": "apps.analytics.tasks.recompute_today",
        "schedule": crontab(minute="*/5"),
    },
    # Har kecha 01:00 da o'tgan kunni yakuniy hisoblash + bozor narxi
    "recompute-yesterday": {
        "task": "apps.analytics.tasks.recompute_yesterday",
        "schedule": crontab(hour=1, minute=0),
    },
    # Har kecha 02:30 da zaxira nusxa (baza + fotolar, tashqi joyga)
    "nightly-backup": {
        "task": "apps.core.tasks.nightly_backup",
        "schedule": crontab(hour=2, minute=30),
    },
    # Har kuni 20:00 da sotuvchilarga kun yakuni/kassa yopishni eslatish
    "close-reminders": {
        "task": "apps.sales.tasks.close_reminders",
        "schedule": crontab(hour=20, minute=0),
    },
}
