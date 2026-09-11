"""Celery ilovasini Django ishga tushganda import qilamiz."""

from .celery import app as celery_app

__all__ = ("celery_app",)
