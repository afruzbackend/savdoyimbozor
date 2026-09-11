"""Soxta kamera hodisalari — kamerasiz "jonli" demo uchun.

    python manage.py simulate_camera --days 7

Har faol do'konga peshtaxta kamerasi yaratadi va xaridor tashriflarini (visit)
generatsiya qiladi. Tashriflar soni kiritilgan savdoga mos: camera_estimate ≈ savdo.
Bitta do'kon uchun ataylab ko'p tashrif (savdoni yashirgan — kamera ko'proq ko'radi).
Bitta kamera "buzilgan" (tamper) qilinadi. So'ng rostlik qayta hisoblanadi.

Kontrakt: hodisalar `CameraEvent` modeli va /api/events/ formatida. Real kamera
qo'shilganda faqat manba o'zgaradi, backend o'zgarmaydi.
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.analytics.scoring.services import recompute_for_date
from apps.cameras.models import Camera, CameraEvent
from apps.core.models import SystemSettings
from apps.sales.models import Sale
from apps.shops.models import Shop


class Command(BaseCommand):
    help = "Soxta kamera hodisalarini generatsiya qiladi (jonli demo)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **opts):
        random.seed(7)
        cfg = SystemSettings.get_solo()
        ratio = float(cfg.buyer_ratio) or 0.35
        shops = list(Shop.objects.filter(is_active=True).select_related("market"))
        if not shops:
            self.stdout.write("Do'kon yo'q. Avval seed_demo bajaring.")
            return

        # Har do'konga peshtaxta kamerasi
        cams = {}
        for s in shops:
            cam, _ = Camera.objects.get_or_create(
                shop=s,
                kind=Camera.Kind.COUNTER,
                defaults={"market": s.market, "name": f"№{s.number} peshtaxta"},
            )
            cam.last_seen = timezone.now()
            cam.status = Camera.Status.ONLINE
            cam.save(update_fields=["last_seen", "status"])
            cams[s.id] = cam

        # Savdoni yashirgan (kamera ko'proq ko'radi) — 2-do'kon
        app_under = shops[2].id if len(shops) > 2 else None

        today = timezone.localdate()
        CameraEvent.objects.filter(type=CameraEvent.Type.VISIT).delete()
        total_events = 0
        for d in range(opts["days"]):
            day = today - timedelta(days=d)
            for s in shops:
                sales = list(Sale.objects.filter(shop=s, created_at__date=day))
                n = len(sales)
                if not n:
                    continue
                visits = max(1, round(n / ratio))
                if s.id == app_under:
                    visits = int(visits * 1.8)  # kamera haqiqiy oqimni ko'radi
                for _ in range(visits):
                    ts = timezone.make_aware(
                        timezone.datetime.combine(day, timezone.datetime.min.time())
                        + timedelta(hours=random.randint(8, 19), minutes=random.randint(0, 59))
                    )
                    CameraEvent.objects.create(
                        camera=cams[s.id],
                        shop=s,
                        type=CameraEvent.Type.VISIT,
                        count=1,
                        ts=ts,
                        payload={
                            "dwell_seconds": random.randint(6, 40),
                            "track_id": f"t{random.randint(1000,9999)}",
                        },
                    )
                    total_events += 1

        # Bitta kamera buzilgan
        victim = cams[shops[0].id]
        victim.status = Camera.Status.TAMPERED
        victim.save(update_fields=["status"])
        CameraEvent.objects.create(
            camera=victim,
            shop=shops[0],
            type=CameraEvent.Type.TAMPER,
            count=1,
            ts=timezone.now(),
            payload={"kind": "covered", "duration_seconds": 45},
        )

        for d in range(opts["days"]):
            recompute_for_date(today - timedelta(days=d))

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(cams)} kamera, {total_events} tashrif hodisasi yaratildi. Rostlik yangilandi."
            )
        )
