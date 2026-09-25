"""Core fon vazifalari (Celery beat)."""

from celery import shared_task
from django.core.management import call_command


@shared_task
def nightly_backup():
    """Har kecha zaxira nusxa (baza + fotolar) — tashqi joyga yuborish bilan."""
    call_command("backup")
