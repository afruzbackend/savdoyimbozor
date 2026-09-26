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
        shops = list(Shop.objects.filter(is_active=True).select_related("market", "category"))
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
                # Halol do'kon uchun kamera bahosi = yozilgan savdo: ulush savdo turiniki
                shop_ratio = float(s.category.buyer_ratio) if s.category and s.category.buyer_ratio else ratio
                visits = max(1, round(n / shop_ratio))
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

        gate_events = self._gate(shops, today, opts["days"])

        from apps.analytics.gate import check_day

        gate_alerts = 0
        for d in range(opts["days"]):
            recompute_for_date(today - timedelta(days=d))
            gate_alerts += check_day(today - timedelta(days=d))

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(cams)} kamera, {total_events} tashrif, {gate_events} darvoza hodisasi "
                f"({gate_alerts} hujjatsiz kirim signali). Rostlik yangilandi."
            )
        )

    def _gate(self, shops, today, days):
        """Darvoza kamerasi: har kirimdan oldin tushirish (mos) + bitta do'konga hujjatsiz tushirish."""
        from apps.sales.models import StockIn

        gates = {}
        for s in shops:
            if s.market_id not in gates:
                cam, _ = Camera.objects.get_or_create(
                    market=s.market, kind=Camera.Kind.GATE, shop=None,
                    defaults={"name": "Asosiy darvoza (ANPR)"},
                )
                cam.last_seen = timezone.now()
                cam.status = Camera.Status.ONLINE
                cam.save(update_fields=["last_seen", "status"])
                gates[s.market_id] = cam
        CameraEvent.objects.filter(type=CameraEvent.Type.GATE_IN).delete()
        since = today - timedelta(days=days - 1)
        n = 0

        def plate():
            return f"01{random.choice('ABDEHKMNS')}{random.randint(100, 999)}{random.choice('ABDEHKMNS')}{random.choice('ABDEHKMNS')}"

        for si in StockIn.objects.filter(shop__in=shops, created_at__date__gte=since).select_related("shop"):
            CameraEvent.objects.create(
                camera=gates[si.shop.market_id], shop=si.shop, type=CameraEvent.Type.GATE_IN,
                count=(c := random.randint(1, 6)), payload={"plate": plate(), "count": c},
                ts=si.created_at - timedelta(minutes=random.randint(15, 70)),
            )
            n += 1
        # Hujjatsiz kirim: tovar keladi, lekin kirim yozilmaydi (keyin chekmas sotiladi)
        hider = shops[4] if len(shops) > 4 else shops[-1]
        for d in range(days):
            day = today - timedelta(days=d)
            for hh, mm in ((7, 20), (15, 5)):
                ts = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time())
                                         + timedelta(hours=hh, minutes=mm))
                if ts > timezone.now():
                    continue
                CameraEvent.objects.create(
                    camera=gates[hider.market_id], shop=hider, type=CameraEvent.Type.GATE_IN,
                    count=(c := random.randint(4, 9)), payload={"plate": plate(), "count": c}, ts=ts,
                )
                n += 1
        return n
