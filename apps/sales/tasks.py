"""Sotuv fon vazifalari (Celery). Beat bo'lmasa — management command sifatida ham ishlaydi."""

from celery import shared_task
from django.core.management import call_command


@shared_task
def close_reminders():
    """Kunlik eslatma: sotuvchilarga kun yakuni + kassa yopish (20:00)."""
    call_command("close_reminders")
