"""
Tahlil xizmatlari: kunlik statistika, xavf balli, o'xshash do'konlar bilan solishtirish.

Formulalar sodda va shaffof — inspektor tushunishi va sudda tushuntirishi oson bo'lishi kerak.
Kamera qo'shilgandan keyin `visitor_count` real AI ma'lumoti bilan to'ladi;
hozircha sotuvchi kiritgan savdoga tayanamiz.
"""
from datetime import date as date_cls
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from events.models import CustomerVisit, Sale
from markets.models import Shop

from .models import Alert, DailyShopStat, Declaration


def compute_daily_stat(shop: Shop, day: date_cls) -> DailyShopStat:
    """Bitta do'kon uchun bitta kunlik statistikani hisoblab, saqlaydi."""
    # AI xaridorlari (kamera bo'lsa)
    visits = CustomerVisit.objects.filter(
        shop=shop, timestamp__date=day,
        dwell_seconds__gte=settings.VISITOR_MIN_DWELL_SECONDS,
    )
    visitor_count = visits.count()

    # Sotuvchi kiritgan savdo
    recorded = Sale.objects.filter(shop=shop, created_at__date=day).aggregate(
        s=Sum("total_amount"))["s"] or Decimal("0")

    # AI taxmini: xaridorlar soni * toifaning o'rtacha chek qiymati
    avg_ticket = shop.category.avg_ticket if shop.category_id else Decimal("0")
    estimated = Decimal(visitor_count) * avg_ticket

    stat, _ = DailyShopStat.objects.update_or_create(
        shop=shop, date=day,
        defaults={
            "visitor_count": visitor_count,
            "recorded_sales": recorded,
            "estimated_sales": estimated,
        },
    )
    return stat


def compute_all_daily_stats(day: date_cls | None = None):
    day = day or timezone.localdate()
    for shop in Shop.objects.filter(is_active=True):
        compute_daily_stat(shop, day)


def declared_vs_estimated_ratio(shop: Shop, year: int, month: int):
    """Oy bo'yicha: deklaratsiya / AI taxmini. 1 ga yaqin = halol; kichik = yashiryapti."""
    decl = Declaration.objects.filter(shop=shop, year=year, month=month).first()
    if not decl:
        return None
    stats = DailyShopStat.objects.filter(
        shop=shop, date__year=year, date__month=month)
    est = stats.aggregate(s=Sum("estimated_sales"))["s"] or Decimal("0")
    # AI taxmini bo'lmasa (kamerasiz), kiritilgan savdoni asos qilamiz
    if est == 0:
        est = stats.aggregate(s=Sum("recorded_sales"))["s"] or Decimal("0")
    if est == 0:
        return None
    return float(decl.declared_amount) / float(est)


def risk_level_from_ratio(ratio: float) -> str:
    if ratio is None:
        return Alert.Level.GREEN
    if ratio < settings.RISK_RED_THRESHOLD:
        return Alert.Level.RED
    if ratio < settings.RISK_YELLOW_THRESHOLD:
        return Alert.Level.YELLOW
    return Alert.Level.GREEN


def peer_comparison(shop: Shop, day: date_cls):
    """O'xshash do'konlar bilan solishtirish. Eng kuchli yashiruvchini aniqlash usuli.

    Qaytaradi: (shop_visitors, peer_avg_visitors, shop_sales, peer_avg_sales).
    """
    peers = shop.similar_shops()
    peer_stats = DailyShopStat.objects.filter(shop__in=peers, date=day)
    my = DailyShopStat.objects.filter(shop=shop, date=day).first()

    n = peers.count() or 1
    peer_visitors = (peer_stats.aggregate(s=Sum("visitor_count"))["s"] or 0) / n
    peer_sales = (peer_stats.aggregate(s=Sum("recorded_sales"))["s"] or Decimal("0")) / n
    return {
        "shop_visitors": my.visitor_count if my else 0,
        "peer_avg_visitors": round(peer_visitors, 1),
        "shop_sales": my.recorded_sales if my else Decimal("0"),
        "peer_avg_sales": round(peer_sales, 2),
        "peer_count": peers.count(),
    }


def generate_alerts(day: date_cls | None = None):
    """Kunlik signal yaratish: o'xshash do'konlardan keskin past savdo → signal."""
    day = day or timezone.localdate()
    created = []
    for shop in Shop.objects.filter(is_active=True):
        # Yopiq kunda signal bermaymiz
        if day.weekday() in shop.closed_weekday_list():
            continue
        cmp = peer_comparison(shop, day)
        if cmp["peer_count"] < 3:
            continue  # solishtirishga yetarli o'xshash do'kon yo'q
        peer_sales = float(cmp["peer_avg_sales"])
        my_sales = float(cmp["shop_sales"])
        if peer_sales <= 0:
            continue
        ratio = my_sales / peer_sales
        level = None
        if ratio < settings.RISK_RED_THRESHOLD:
            level = Alert.Level.RED
        elif ratio < settings.RISK_YELLOW_THRESHOLD:
            level = Alert.Level.YELLOW
        if level:
            # Shu kun uchun takroriy signal yaratmaymiz
            if Alert.objects.filter(shop=shop, date=day).exists():
                continue
            msg = (f"O'xshash do'konlardan {round((1-ratio)*100)}% past savdo "
                   f"({int(my_sales):,} vs o'rtacha {int(peer_sales):,} so'm)")
            alert = Alert.objects.create(
                shop=shop, date=day, level=level, message=msg,
                assigned_to=shop.market.inspectors.first(),
            )
            created.append(alert)
    return created
