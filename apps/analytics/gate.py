"""Darvoza kamerasi ↔ kirim: tovar tushirilgan, lekin kirim yozilmagan ("hujjatsiz kirim").

Kamera kontrakti o'zgarmaydi: `gate_in` hodisasi (shop_id, payload.count — qop/quti soni,
payload.plate — mashina raqami). Har tushirish hodisasi o'sha do'konning [−2 soat, +14 soat]
oralig'idagi istalgan StockIn bilan qoplanadi (bitta yetkazib berish — bir nechta mahsulot
qatori bo'lishi mumkin, shuning uchun yumshoq moslash: yolg'on signal kam).

Qoplanmagan tushirish = tovar kelgan, ammo tizimga yozilmagan → keyin chekmas sotiladi,
qoldiq/rostlik solishtiruvidan ham yashiriladi. Kun tugab, oxirgi hodisa oynasi yopilgach
(ertasi 14:00) tekshiriladi — sotuvchi kirimni ertalab kiritishga ulgursin.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from django.utils import timezone

WINDOW_BEFORE = datetime.timedelta(hours=2)
WINDOW_AFTER = datetime.timedelta(hours=14)


def _day_bounds(day):
    start = timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))
    return start, start + datetime.timedelta(days=1)


def deliveries(shop_ids, day) -> dict[int, list]:
    """{shop_id: [gate_in hodisalari]} — faqat do'konga bog'langanlari."""
    from apps.cameras.models import CameraEvent

    start, end = _day_bounds(day)
    out = defaultdict(list)
    for ev in CameraEvent.objects.filter(
        type=CameraEvent.Type.GATE_IN, shop_id__in=shop_ids, ts__gte=start, ts__lt=end
    ).order_by("ts"):
        out[ev.shop_id].append(ev)
    return out


def match(events, stockin_times) -> tuple[list, list]:
    """(qoplangan, qoplanmagan) hodisalar. stockin_times — o'sha do'kon kirim vaqtlari."""
    covered, missing = [], []
    for ev in events:
        lo, hi = ev.ts - WINDOW_BEFORE, ev.ts + WINDOW_AFTER
        (covered if any(lo <= t <= hi for t in stockin_times) else missing).append(ev)
    return covered, missing


def _stockin_times(shop_ids, day) -> dict[int, list]:
    from apps.sales.models import StockIn

    start, end = _day_bounds(day)
    out = defaultdict(list)
    for sid, ts in StockIn.objects.filter(
        shop_id__in=shop_ids, created_at__gte=start - WINDOW_BEFORE,
        created_at__lt=end + WINDOW_AFTER,
    ).values_list("shop_id", "created_at"):
        out[sid].append(ts)
    return out


def window_closed(day, now=None) -> bool:
    now = now or timezone.now()
    return now >= _day_bounds(day)[1] + WINDOW_AFTER


def check_day(day, *, force=False) -> int:
    """Kun uchun hujjatsiz kirim signallari. Oyna yopilmagan bo'lsa (force'siz) — hech narsa."""
    from apps.analytics.models import Alert
    from apps.shops.models import Shop

    if not force and not window_closed(day):
        return 0
    by_shop = deliveries(list(Shop.objects.filter(is_active=True).values_list("pk", flat=True)),
                         day)
    if not by_shop:
        return 0
    times = _stockin_times(list(by_shop), day)
    already = set(Alert.objects.filter(date=day, kind=Alert.Kind.GATE_UNRECORDED,
                                       shop_id__in=list(by_shop)).values_list("shop_id", flat=True))
    created = 0
    for shop in Shop.objects.filter(pk__in=list(by_shop)).select_related("market"):
        if shop.pk in already:
            continue
        _covered, missing = match(by_shop[shop.pk], times.get(shop.pk, []))
        if not missing:
            continue
        units = sum(ev.count or 1 for ev in missing)
        hours = ", ".join(timezone.localtime(ev.ts).strftime("%H:%M") for ev in missing[:4])
        if len(missing) > 4:
            hours += " …"
        plates = sorted({str(ev.payload.get("plate")) for ev in missing if ev.payload.get("plate")})
        level = "red" if len(missing) >= 2 or units >= 10 else "yellow"
        reason = (f"Darvoza kamerasi {len(missing)} marta tovar tushirishni ko'rdi ({hours}; "
                  f"~{units} qop/quti), lekin kirim yozilmagan")
        if plates:
            reason += f" · mashina: {', '.join(plates[:3])}"
        alert = Alert.objects.create(
            shop=shop, date=day, kind=Alert.Kind.GATE_UNRECORDED, level=level,
            reason=reason[:300], assigned_to=shop.market.duty_inspector(),
        )
        created += 1
        if level == "red":
            try:
                from apps.analytics.notifications import notify_alert

                notify_alert(alert)
            except Exception:  # noqa: BLE001 — xabar asosiy oqimni buzmasin
                pass
    return created


def shop_summary(shop, days=14) -> list[dict]:
    """Do'kon sahifasi uchun: kunlar bo'yicha tushirish vs kirim (faqat hodisa bo'lgan kunlar)."""
    from apps.cameras.models import CameraEvent

    today = timezone.localdate()
    start, _ = _day_bounds(today - datetime.timedelta(days=days - 1))
    events = list(CameraEvent.objects.filter(type=CameraEvent.Type.GATE_IN, shop=shop,
                                             ts__gte=start).order_by("ts"))
    if not events:
        return []
    by_day = defaultdict(list)
    for ev in events:
        by_day[timezone.localtime(ev.ts).date()].append(ev)
    rows = []
    for day in sorted(by_day, reverse=True):
        times = _stockin_times([shop.pk], day).get(shop.pk, [])
        covered, missing = match(by_day[day], times)
        rows.append({
            "date": day,
            "events": len(by_day[day]),
            "units": sum(ev.count or 1 for ev in by_day[day]),
            "stockins": sum(1 for t in times if timezone.localtime(t).date() == day),
            "missing": [timezone.localtime(ev.ts) for ev in missing],
            "pending": not window_closed(day),
        })
    return rows
