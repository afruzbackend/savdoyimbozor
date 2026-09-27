"""Core fon vazifalari (Celery beat)."""

from celery import shared_task
from django.core.management import call_command


@shared_task
def nightly_backup():
    """Har kecha zaxira nusxa (baza + fotolar) — tashqi joyga yuborish bilan."""
    call_command("backup")


@shared_task
def heartbeat():
    """Har daqiqa: "fon vazifalari tirik" belgisi (/healthz/ va panel kartasi tekshiradi)."""
    from apps.core.health import beat

    beat()


@shared_task
def clear_sessions():
    """Muddati o'tgan sessiyalarni o'chiradi — django_session jadvali yillar davomida cheksiz o'smasin."""
    call_command("clearsessions")
