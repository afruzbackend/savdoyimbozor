"""Topshirish/deploy oldidan tekshiruv — DEPLOY.md dagi ro'yxat avtomatik.

    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py preflight

[XATO] bo'lsa chiqish kodi 1 (CI/skript to'xtaydi). [OGOH] — ishlaydi, lekin topshirishdan oldin hal qiling.
Lokal http demo uchun: --allow-http (HTTPS talablari tekshirilmaydi).
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

DEMO_USERNAMES = ("admin", "nazorat", "sotuvchi", "prokuror")
DEMO_PASSWORD = "demo1234"  # seed_demo paroli — prod bazada bo'lmasligi SHART


class Command(BaseCommand):
    help = "Deploy/topshirishdan oldin xavfsizlik va tayyorlik tekshiruvi"

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-http", action="store_true", help="Lokal http demo: HTTPS talab qilinmaydi"
        )

    def handle(self, *args, **opts):
        self.fails = 0
        self.warns = 0
        https = not opts["allow_http"]

        self.section("Sozlamalar")
        self._chk(
            not settings.DEBUG,
            "DEBUG o'chiq",
            "DEBUG=True — xato sahifalari kod va sozlamani oshkor qiladi",
        )
        key = settings.SECRET_KEY or ""
        self._chk(
            len(key) >= 40 and key not in ("dev-insecure-change-me", "change-me-in-production"),
            "SECRET_KEY kuchli",
            "SECRET_KEY qisqa yoki standart",
        )
        hosts = [h for h in settings.ALLOWED_HOSTS if h]
        self._chk(
            hosts and "*" not in hosts,
            f"ALLOWED_HOSTS: {', '.join(hosts)}",
            "ALLOWED_HOSTS bo'sh yoki '*'",
        )
        if https:
            self._chk(
                settings.SECURE_SSL_REDIRECT,
                "HTTP so'rovlar HTTPS ga yo'naltiriladi",
                "SECURE_SSL_REDIRECT o'chiq",
            )
            self._chk(
                settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
                "Cookie faqat HTTPS orqali",
                "SESSION/CSRF_COOKIE_SECURE o'chiq",
            )
            self._chk(
                settings.SECURE_HSTS_SECONDS >= 31536000, "HSTS 1 yil", "HSTS o'chiq yoki qisqa"
            )
            origins = settings.CSRF_TRUSTED_ORIGINS or []
            self._chk(
                origins and all(o.startswith("https://") for o in origins),
                "CSRF_TRUSTED_ORIGINS https",
                "CSRF_TRUSTED_ORIGINS bo'sh yoki http",
            )
            base = getattr(settings, "PUBLIC_BASE_URL", "")
            self._chk(
                base.startswith("https://"),
                f"PUBLIC_BASE_URL: {base}",
                "PUBLIC_BASE_URL bo'sh yoki https emas (xaridor QR cheki ochilmaydi)",
            )
        self._chk(
            settings.TIME_ZONE == "Asia/Tashkent",
            "Vaqt zonasi Asia/Tashkent",
            "TIME_ZONE noto'g'ri",
            warn_only=True,
        )
        self._chk(
            bool(getattr(settings, "BACKUP_UPLOAD_CMD", "")),
            "Zaxira tashqariga yuboriladi",
            "BACKUP_UPLOAD_CMD bo'sh — zaxira faqat shu serverda qoladi",
        )
        self._chk(
            bool(getattr(settings, "SENTRY_DSN", "")),
            "Xato kuzatuvi (SENTRY_DSN) ulangan",
            "SENTRY_DSN bo'sh — xatolar faqat logda",
            warn_only=True,
        )
        self._chk(
            bool(getattr(settings, "HEALTH_TOKEN", "")),
            "HEALTH_TOKEN o'rnatilgan",
            "HEALTH_TOKEN bo'sh — monitoring batafsil holatni ko'rmaydi",
            warn_only=True,
        )

        self.section("Baza va xizmatlar")
        try:
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor

            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            self._chk(
                not plan,
                "Barcha migratsiyalar qo'llangan",
                f"{len(plan)} ta migratsiya qo'llanmagan — python manage.py migrate",
            )
        except Exception as e:  # noqa: BLE001
            self._chk(False, "", f"Bazaga ulanib bo'lmadi: {e}")
            return self.summary()
        backend = settings.CACHES["default"]["BACKEND"]
        self._chk(
            "locmem" not in backend.lower(),
            "Kesh umumiy (Redis)",
            "Kesh jarayon ichida (LocMem) — gunicorn worker'lari orasida login bloki, API chegarasi "
            "va sozlamalar keshi umumiy emas. CACHE_URL=redis://... qo'ying",
            warn_only=not https,
        )
        from apps.core import health

        for c in health.run(full=True)["checks"]:
            if c["status"] == "fail":
                self._chk(False, "", f"{c['name']}: {c['detail']}")
            elif c["status"] == "warn":
                self._chk(False, "", f"{c['name']}: {c['detail']}", warn_only=True)
            else:
                self.stdout.write(f"  [OK]    {c['name']}: {c['detail']}")
        if "StaticStorage" in str(settings.STORAGES.get("staticfiles", {}).get("BACKEND", "")):
            from pathlib import Path

            self._chk(
                (Path(settings.STATIC_ROOT) / "staticfiles.json").exists(),
                "Statik fayllar yig'ilgan (collectstatic)",
                "staticfiles.json yo'q — python manage.py collectstatic",
            )

        self.section("Hisoblar")
        from django.db.models import Q

        from apps.accounts.models import Role, User
        from apps.core.models import SystemSettings

        self._chk(
            User.objects.filter(role=Role.SUPERADMIN, is_active=True).exists(),
            "Bosh admin bor",
            "Faol bosh admin yo'q — python manage.py createsuperuser",
        )
        # seed_demo loginlari/paroli prod bazada qolmasin (hammaga ma'lum parol). Parol tekshiruvi
        # sekin (PBKDF2) — faqat demo loginlar va bosh adminlar tekshiriladi
        suspects = User.objects.filter(is_active=True).filter(
            Q(username__in=DEMO_USERNAMES) | Q(role=Role.SUPERADMIN)
        )[:50]
        demo = [u.username for u in suspects if u.check_password(DEMO_PASSWORD)]
        self._chk(
            not demo,
            "Demo parolli hisob yo'q",
            f"'{DEMO_PASSWORD}' parolli hisoblar: {', '.join(demo[:10])} — seed_demo ishlatilgan! "
            "O'chiring yoki parolini tiklang",
        )
        cfg = SystemSettings.get_solo()
        self._chk(
            cfg.require_2fa_staff,
            "Xodimlarga 2FA majburiy",
            "Xodimlarga 2FA majburiy EMAS — Panel > Sozlamalar",
            warn_only=True,
        )
        no2fa = (
            User.objects.filter(is_active=True)
            .exclude(role=Role.SELLER)
            .filter(totp_enabled=False)
            .count()
        )
        self._chk(
            no2fa == 0,
            "Barcha xodimlarda 2FA yoqilgan",
            f"{no2fa} ta xodimda 2FA yoqilmagan",
            warn_only=True,
        )
        return self.summary()

    # ---- yordamchilar ----
    def section(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))

    def _chk(self, ok, good, bad, warn_only=False):
        if ok:
            self.stdout.write(f"  [OK]    {good}")
        elif warn_only:
            self.warns += 1
            self.stdout.write(self.style.WARNING(f"  [OGOH]  {bad}"))
        else:
            self.fails += 1
            self.stdout.write(self.style.ERROR(f"  [XATO]  {bad}"))

    def summary(self):
        self.stdout.write("")
        if self.fails:
            self.stdout.write(
                self.style.ERROR(
                    f"{self.fails} ta XATO, {self.warns} ta ogohlantirish — "
                    "deploy/topshirishga TAYYOR EMAS"
                )
            )
            raise SystemExit(1)
        msg = f"XATO yo'q, {self.warns} ta ogohlantirish" if self.warns else "Hammasi tayyor"
        self.stdout.write(self.style.SUCCESS(msg))
