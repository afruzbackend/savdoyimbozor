"""Demo ma'lumot — taqdimot va sinov uchun realistik ko'rinishli.

    python manage.py seed_demo --reset

1 viloyat, 1 bozor, 4 qator, ~24 do'kon (meva-sabzavot/kiyim/oziq-ovqat), 7 kunlik savdo
va deklaratsiya. 3-4 do'kon ataylab "yashiruvchi" (kassa yashiradi / narx past) —
nazorat xaritasida qizil chiqadi. Oxirida barcha loginlar chiqariladi.
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.analytics.models import Alert, Appeal, DailyScore, Inspection, MarketPrice
from apps.analytics.scoring.services import recompute_for_date
from apps.cameras.models import Camera, CameraEvent
from apps.cash.models import CashRecord
from apps.catalog.models import Product, ProductCategory, ShopCategory, Unit
from apps.geo.models import Market, Region, Row
from apps.sales.models import (
    Correction,
    DailyClose,
    DailyCloseLine,
    Debt,
    RegisterClose,
    Sale,
    SaleItem,
    SaleReturn,
    StockIn,
    WriteOff,
)
from apps.shops.models import Shop

User = get_user_model()
PW = "demo1234"

# toifa -> (mahsulotlar: nom, birlik, bozor_narxi)
CATALOG = {
    "Meva-sabzavot": [
        ("Pomidor", Unit.KG, 12000),
        ("Bodring", Unit.KG, 10000),
        ("Kartoshka", Unit.KG, 6000),
        ("Olma", Unit.KG, 15000),
        ("Piyoz", Unit.KG, 5000),
        ("Sabzi", Unit.KG, 6000),
        ("Karam", Unit.KG, 5000),
        ("Uzum", Unit.KG, 20000),
        ("Banan", Unit.KG, 22000),
        ("Nok", Unit.KG, 18000),
        ("Anor", Unit.KG, 17000),
        ("Limon", Unit.KG, 24000),
        ("Sarimsoq", Unit.KG, 30000),
        ("Qalampir", Unit.KG, 14000),
        ("Ko'katlar", Unit.BUNDLE, 3000),
    ],
    "Kiyim-kechak": [
        ("Kurtka", Unit.PIECE, 250000),
        ("Ko'ylak", Unit.PIECE, 120000),
        ("Shim", Unit.PIECE, 150000),
        ("Poyabzal", Unit.PIECE, 200000),
        ("Bosh kiyim", Unit.PIECE, 45000),
        ("Paypoq", Unit.PIECE, 10000),
        ("Futbolka", Unit.PIECE, 60000),
    ],
    "Oziq-ovqat": [
        ("Un", Unit.KG, 8000),
        ("Guruch", Unit.KG, 14000),
        ("Yog'", Unit.LITER, 22000),
        ("Shakar", Unit.KG, 12000),
        ("Tuxum", Unit.PIECE, 1200),
        ("Makaron", Unit.KG, 11000),
        ("Choy", Unit.PIECE, 15000),
        ("Tuz", Unit.KG, 3000),
    ],
}
ROWS = ["Meva qatori", "Sabzavot qatori", "Kiyim qatori", "Oziq-ovqat qatori"]


class Command(BaseCommand):
    help = "Demo ma'lumot yaratadi (bozor, do'kon, savdo, deklaratsiya, signal)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Avval tozalaydi")
        parser.add_argument("--days", type=int, default=7)

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(2026)
        if opts["reset"]:
            for M in (
                CameraEvent,
                Camera,
                Inspection,
                Appeal,
                Alert,
                DailyScore,
                MarketPrice,
                DailyCloseLine,
                DailyClose,
                SaleItem,
                Sale,
                SaleReturn,
                WriteOff,
                StockIn,
                Correction,
                RegisterClose,
                Debt,
                CashRecord,
                Product,
                ProductCategory,
                Shop,
                Row,
                ShopCategory,
                Market,
                Region,
            ):
                M.objects.all().delete()
            # Yetim/eski foydalanuvchilarni tozalaymiz (demo loginlar va superuser saqlanadi)
            from apps.accounts.models import User

            User.objects.exclude(is_superuser=True).exclude(
                username__in=["admin", "nazorat", "sotuvchi"]
            ).delete()
            self.stdout.write("Eski ma'lumot tozalandi.")

        region, _ = Region.objects.get_or_create(name="Toshkent shahri", defaults={"code": "10"})
        market, _ = Market.objects.get_or_create(
            region=region,
            name="Chorsu bozori",
            defaults={"address": "Chorsu, Olmazor", "latitude": 41.3110, "longitude": 69.2797},
        )
        MLAT, MLNG = 41.3110, 69.2797  # xarita markazi (do'konlar shu atrofda tarqaladi)
        rows = {
            name: Row.objects.get_or_create(market=market, label=name, defaults={"order": i})[0]
            for i, name in enumerate(ROWS)
        }

        shop_cats, prod_cats = {}, {}
        for scat, products in CATALOG.items():
            sc, _ = ShopCategory.objects.get_or_create(name=scat)
            shop_cats[scat] = sc
            for pname, unit, _price in products:
                pc, _ = ProductCategory.objects.get_or_create(
                    name=pname, defaults={"shop_category": sc, "default_unit": unit}
                )
                prod_cats[pname] = pc

        # Do'konlarni yaratamiz
        layout = [
            ("Meva-sabzavot", "Meva qatori", 8),
            ("Meva-sabzavot", "Sabzavot qatori", 6),
            ("Kiyim-kechak", "Kiyim qatori", 6),
            ("Oziq-ovqat", "Oziq-ovqat qatori", 4),
        ]
        shops = []
        num = 1
        for scat, rowname, n in layout:
            ri = ROWS.index(rowname)
            for j in range(n):
                lat = MLAT + (ri - 1.5) * 0.0011 + random.uniform(-0.0003, 0.0003)
                lng = MLNG + (j - 3) * 0.0013 + random.uniform(-0.0004, 0.0004)
                shop, _ = Shop.objects.get_or_create(
                    market=market,
                    number=str(num),
                    defaults={
                        "stir": f"3{num:08d}",
                        "owner_name": self._name(num),
                        "owner_phone": f"+99890{random.randint(1000000,9999999)}",
                        "category": shop_cats[scat],
                        "row": rows[rowname],
                        "map_x": (j % 6) * 90 + 40,
                        "map_y": ri * 90 + 40,
                        "latitude": round(lat, 6),
                        "longitude": round(lng, 6),
                    },
                )
                # Mahsulotlar
                for pi, (pname, unit, price) in enumerate(CATALOG[scat]):
                    Product.objects.get_or_create(
                        shop=shop,
                        name=pname,
                        defaults={
                            "category": prod_cats[pname],
                            "unit": unit,
                            "sell_price": price,
                            "buy_price": int(price * 0.72),
                            "stock": random.randint(50, 300),
                            "barcode": f"20{num:04d}{pi}",
                        },
                    )
                shops.append((shop, scat))
                num += 1

        # Chegirma pog'onalarini yangilaymiz (mavjud sozlama yozuvi eski bo'lishi mumkin)
        from apps.core.models import SystemSettings

        st = SystemSettings.get_solo()
        st.discount_tiers = SystemSettings.DEFAULT_DISCOUNT_TIERS
        st.discount_percents = SystemSettings.DEFAULT_DISCOUNT_PERCENTS
        st.save()

        # Yashiruvchilar: kassa / narx / qoldiq
        cash_hiders = {shops[0][0].id, shops[9][0].id, shops[15][0].id}
        price_hider = shops[3][0].id
        stock_hiders = {shops[6][0].id, shops[18][0].id}  # kun yakunida qoldiqni yashiradi
        # Narx yashiruvchisi: har mahsulotni bozor narxining ~42% ига tushiradi
        price_map = {pn: pr for prods in CATALOG.values() for pn, _u, pr in prods}
        for p in Product.objects.filter(shop_id=price_hider):
            if p.name in price_map:
                p.sell_price = int(price_map[p.name] * 0.42)
                p.save(update_fields=["sell_price"])

        # Foydalanuvchilar
        self._user("admin", "Bosh Admin", "superadmin", is_super=True)
        insp = self._user("nazorat", "Nodir Inspektor", "inspector")
        insp.assigned_markets.add(market)
        self._user("sotuvchi", "Sardor Sotuvchi", "seller", shop=shops[1][0], is_owner=True)

        # 7 kunlik savdo + deklaratsiya
        today = timezone.localdate()
        for d in range(opts["days"]):
            day = today - timedelta(days=d)
            for shop, scat in shops:
                self._gen_day(shop, scat, day, prod_cats, is_cash_hider=shop.id in cash_hiders)
                self._gen_close(shop, day, is_stock_hider=shop.id in stock_hiders)
                self._gen_register_close(shop, day, is_cash_hider=shop.id in cash_hiders)

        # Rostlik + signal
        for d in range(opts["days"]):
            recompute_for_date(today - timedelta(days=d))

        reds = Alert.objects.filter(level="red").values("shop").distinct().count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo tayyor: {len(shops)} do'kon, {opts['days']} kun. "
                f"Qizil signalli do'konlar: {reds}."
            )
        )
        self.stdout.write("Loginlar (parol demo1234): admin / nazorat / sotuvchi")

    def _gen_day(self, shop, scat, day, prod_cats, is_cash_hider):
        base = {"Meva-sabzavot": 2_500_000, "Kiyim-kechak": 4_000_000, "Oziq-ovqat": 1_800_000}[
            scat
        ]
        target = int(base * random.uniform(0.7, 1.3))
        products = list(Product.objects.filter(shop=shop))
        remaining = target
        while remaining > 20_000 and products:
            p = random.choice(products)
            qty = random.randint(1, 5) if p.unit != Unit.KG else round(random.uniform(0.5, 8), 1)
            line = int(qty * p.sell_price)
            if line <= 0:
                break
            dt = timezone.make_aware(
                timezone.datetime.combine(day, timezone.datetime.min.time())
                + timedelta(hours=random.randint(8, 18), minutes=random.randint(0, 59))
            )
            # Ba'zi cheklarga chegirma (savdolashish) — tannarxdan past emas
            disc = 0
            if random.random() < 0.3:
                cap = max(0, line - int(qty * p.buy_price))  # tannarx cheklovi
                disc = int(min(round(line * random.uniform(0.02, 0.08), -3), cap))
            sale = Sale.objects.create(
                shop=shop,
                total=line - disc,
                subtotal=line,
                discount=disc,
                payment_type=random.choice(["cash", "cash", "card"]),
                is_wholesale=random.random() < 0.1,
            )
            # auto_now_add created_at ni bekor qiladi — kerakli sanaga majburan o'zgartiramiz
            Sale.objects.filter(pk=sale.pk).update(created_at=dt)
            SaleItem.objects.create(
                sale=sale,
                product=p,
                product_name=p.name,
                quantity=qty,
                unit_price=p.sell_price,
                line_total=line,
            )
            remaining -= line
        entered = sum(s.total for s in Sale.objects.filter(shop=shop, created_at__date=day))
        # Deklaratsiya: halol ~92-100%, yashiruvchi ~25-40%
        factor = random.uniform(0.25, 0.4) if is_cash_hider else random.uniform(0.9, 1.0)
        CashRecord.objects.update_or_create(
            shop=shop, date=day, source="excel", defaults={"amount": int(entered * factor)}
        )

    def _gen_close(self, shop, day, is_stock_hider):
        """Kun yakuni: sotilgan miqdorni qoldiqqa aylantiradi. Yashiruvchi kam ko'rsatadi."""
        from django.db.models import Sum

        rows = (
            SaleItem.objects.filter(
                sale__shop=shop, sale__created_at__date=day, product__isnull=False
            )
            .values("product", "product_name", "unit_price")
            .annotate(q=Sum("quantity"))
        )
        if not rows:
            return
        factor = random.uniform(0.3, 0.45) if is_stock_hider else random.uniform(0.95, 1.0)
        close, _ = DailyClose.objects.update_or_create(shop=shop, date=day)
        close.lines.all().delete()
        computed = 0
        for r in rows:
            sold = float(r["q"]) * factor  # ko'rsatilgan sotuv (qoldiq harakati)
            computed += int(sold * r["unit_price"])
            DailyCloseLine.objects.create(
                close=close,
                product_id=r["product"],
                product_name=r["product_name"],
                morning_qty=sold,
                evening_qty=0,
                unit_price=r["unit_price"],
            )
        entered = sum(s.total for s in Sale.objects.filter(shop=shop, created_at__date=day))
        close.computed_sales = computed
        close.entered_sales = entered
        close.save(update_fields=["computed_sales", "entered_sales"])

    def _gen_register_close(self, shop, day, is_cash_hider):
        """Kassa yopish (Z-hisobot): to'lov turi bo'yicha jamlanma + sanalgan naqd.

        Halol do'kon: sanalgan ≈ kutilgan (kichik farq). Yashiruvchi: ataylab
        kam sanaydi (kamomad) — nazoratchiga signal bo'ladi.
        """
        from django.db.models import Count, Sum

        agg = {
            r["payment_type"]: r
            for r in Sale.objects.filter(shop=shop, created_at__date=day)
            .values("payment_type")
            .annotate(s=Sum("total"), n=Count("id"))
        }
        cash = agg.get("cash", {}).get("s") or 0
        card = agg.get("card", {}).get("s") or 0
        transfer = agg.get("transfer", {}).get("s") or 0
        count = sum((agg.get(k, {}).get("n") or 0) for k in ("cash", "card", "transfer"))
        if count == 0:
            return
        if is_cash_hider:
            # Yashiruvchi: sandiqда yozilgandan KO'P naqd (yozilmagan savdo) — ortiqcha
            counted = int(cash * random.uniform(1.3, 1.8))
        else:
            counted = cash + random.choice([0, 0, 0, -5_000, 3_000])  # deyarli mos
        RegisterClose.objects.update_or_create(
            shop=shop,
            date=day,
            defaults={
                "expected_cash": cash,
                "counted_cash": max(0, counted),
                "card_total": card,
                "transfer_total": transfer,
                "checks_count": count,
            },
        )

    def _user(self, username, full, role, is_super=False, shop=None, is_owner=False):
        u, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": full.split()[0],
                "last_name": " ".join(full.split()[1:]),
                "role": role,
            },
        )
        u.role = role
        if is_super:
            u.is_staff = u.is_superuser = True
            u.role = "superadmin"
        u.shop = shop
        u.is_shop_owner = is_owner
        u.must_change_password = False
        u.set_password_visible(PW)  # admin panelida parol ko'rinsin
        u.save()
        return u

    def _name(self, i):
        first = [
            "Karimov",
            "Toshpo'lat",
            "Rahimova",
            "Yusupov",
            "Salimova",
            "Ergashev",
            "Nazarov",
            "Qodirova",
            "Islomov",
            "Xolmatova",
        ]
        return f"{first[i % len(first)]} {chr(65 + i % 26)}."
