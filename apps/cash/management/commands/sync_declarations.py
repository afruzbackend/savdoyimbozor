"""Soliq / onlayn kassa deklaratsiyasini olish.

    python manage.py sync_declarations                    # kecha + oldingi kunlar (TAX_SYNC_DAYS)
    python manage.py sync_declarations --from 2026-09-01 --to 2026-09-24
"""

import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.cash.sync import run_sync


def _date(value):
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as e:
        raise CommandError(f"Sana YYYY-MM-DD bo'lsin: {value}") from e


class Command(BaseCommand):
    help = "Soliq API / kassa operatoridan deklaratsiyani olib, rostlikni qayta hisoblaydi."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="date_from")
        parser.add_argument("--to", dest="date_to")

    def handle(self, *args, **opts):
        date_from = _date(opts["date_from"]) if opts["date_from"] else None
        date_to = _date(opts["date_to"]) if opts["date_to"] else None
        if (date_from is None) != (date_to is None):
            raise CommandError("--from va --to birga beriladi")
        if date_from and date_from > date_to:
            raise CommandError("--from --to dan keyin bo'lmasin")
        entry = run_sync(date_from, date_to)
        if entry is None:
            self.stdout.write(self.style.WARNING("TAX_ADAPTER sozlanmagan — sinxronlash o'chiq."))
            return
        style = self.style.SUCCESS if entry.ok else self.style.ERROR
        self.stdout.write(style(f"{entry.message} Kelgan: {entry.fetched}, "
                                f"bog'lanmagan: {entry.unmatched}."))
        for p in entry.problems[:10]:
            self.stdout.write(f"  - {p}")
