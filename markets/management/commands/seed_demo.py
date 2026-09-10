"""Demo ma'lumot yaratadi — taqdimot va sinov uchun.

    python manage.py seed_demo

Yaratadi: 1 bozor, 4 toifa, ~15 do'kon, foydalanuvchilar (admin/rahbar/inspektor/sotuvchi),
14 kunlik savdolar (bittasi ataylab yashiruvchi), deklaratsiyalar, signallar.
Login parollari: hammasi "demo1234".
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.services import compute_all_daily_stats, generate_alerts
from events.models import Sale
from markets.models import Market, ProductCategory, Shop

User = get_user_model()
PW = "demo1234"


class Command(BaseCommand):
    help = "Demo ma'lumot yaratadi (bozor, do'kon, savdo, signal)."

    def handle(self, *args, **opts):
        random.seed(42)

        market, _ = Market.objects.get_or_create(
            name="Chorsu bozori", defaults={"region": "Toshkent", "address": "Chorsu maydoni"})

        cats = {}
        for name, ticket, waste in [
            ("Meva-sabzavot", 25000, 5), ("Kiyim-kechak", 90000, 1),
            ("Go'sht", 60000, 2), ("Non-shirinlik", 15000, 3)]:
            c, _ = ProductCategory.objects.get_or_create(
                name=name, defaults={"avg_ticket": ticket, "waste_norm_percent": waste})
            cats[name] = c

        # Foydalanuvchilar
        self._user("admin", "Admin", "admin", is_super=True)
        manager = self._user("rahbar", "Rahbar Rahimov", "manager")
        inspector = self._user("inspektor", "Inspektor Islomov", "inspector",
                               market=market)

        # Do'konlar — har toifadan bir nechta (o'xshash do'konlar solishtiruvi uchun)
        shops = []
        catalog = [
            ("Meva-sabzavot", 6), ("Kiyim-kechak", 4), ("Go'sht", 3), ("Non-shirinlik", 2)]
        idx = 1
        for cat_name, count in catalog:
            for j in range(count):
                shop, _ = Shop.objects.get_or_create(
                    market=market, name=f"{cat_name} do'koni #{j+1}",
                    defaults={
                        "stir": f"30{idx:07d}",
                        "owner_name": f"Egasi {idx}",
                        "owner_phone": f"+99890{random.randint(1000000,9999999)}",
                        "category": cats[cat_name],
                        "row_label": f"{cat_name[:3]}-{j+1}",
                    })
                shops.append(shop)
                idx += 1

        # Bitta sotuvchi (birinchi do'konga)
        self._user("sotuvchi", "Sotuvchi Sodiqov", "seller", shop=shops[0])

        # 14 kunlik savdolar. Har toifada bittasi ataylab yashiruvchi.
        today = timezone.localdate()
        hider_ids = set()
        by_cat = {}
        for s in shops:
            by_cat.setdefault(s.category_id, []).append(s)
        for cat_shops in by_cat.values():
            hider_ids.add(cat_shops[0].id)  # har toifaning 1-do'koni yashiradi

        Sale.objects.filter(shop__in=shops).delete()
        for day_offset in range(14):
            day = today - timedelta(days=day_offset)
            for s in shops:
                base = float(s.category.avg_ticket) * random.randint(90, 160)
                if s.id in hider_ids:
                    base *= 0.2  # 80% kamaytirib ko'rsatadi
                # Kunni bir nechta chekka bo'lamiz
                remaining = base
                while remaining > 0:
                    amt = min(remaining, random.uniform(15000, 120000))
                    Sale.objects.create(
                        shop=s, total_amount=Decimal(round(amt, -2)),
                        payment_type=random.choice(["cash", "cash", "card"]))
                    remaining -= amt

        # Statistika va signallar
        for day_offset in range(14):
            compute_all_daily_stats(today - timedelta(days=day_offset))
        for day_offset in range(14):
            generate_alerts(today - timedelta(days=day_offset))

        self.stdout.write(self.style.SUCCESS(
            f"Demo tayyor: {market.name}, {len(shops)} do'kon. "
            f"Loginlar: admin/rahbar/inspektor/sotuvchi — parol: {PW}"))

    def _user(self, username, full, role, is_super=False, market=None, shop=None):
        u, created = User.objects.get_or_create(username=username, defaults={
            "first_name": full.split()[0],
            "last_name": " ".join(full.split()[1:]),
            "role": role,
        })
        u.role = role
        if is_super:
            u.is_staff = True
            u.is_superuser = True
            u.role = "manager"
        u.assigned_market = market
        u.assigned_shop = shop
        u.set_password(PW)
        u.save()
        return u
