"""Sotuvchi API'lari (API-first). Alpine frontend shu endpointlarni chaqiradi."""

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.dates import on_day

from .models import Sale
from .services.sales import DebtorRequired, InsufficientStock, InvalidQuantity, create_sale

log = logging.getLogger(__name__)


def _seller_shop(request):
    return getattr(request.user, "shop", None)


@api_view(["POST"])
def create_sale_api(request):
    """Yangi sotuv. body: {items:[{name,qty,unit_price,product_id?}], discount, rounding,
    payment_type, is_wholesale, mode, client_ts?}"""
    shop = _seller_shop(request)
    if shop is None:
        return Response({"detail": "Do'kon biriktirilmagan."}, status=400)

    data = request.data
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return Response({"detail": "Kamida bitta mahsulot kerak."}, status=400)

    # Kirish tekshiruvi (API-first: mobil ilova ham shu yerga keladi)
    from apps.core.format import to_dec, to_int

    from .models import PaymentType, SaleMode

    clean = []
    for it in items:
        if not isinstance(it, dict):
            return Response({"detail": "Noto'g'ri qator."}, status=400)
        qty = to_dec(it.get("qty"))
        price = to_int(it.get("unit_price"))
        if qty is None or qty <= 0:
            return Response({"detail": "Miqdor 0 dan katta bo'lsin."}, status=400)
        if price is None or price < 0:
            return Response({"detail": "Narx manfiy bo'lmasin."}, status=400)
        clean.append({
            "product_id": to_int(it.get("product_id"), 0) or None,  # "abc" → 500 emas
            "name": str(it.get("name") or "")[:200],
            "qty": qty,
            "unit_price": price,
        })
    # Oflayn navbat bir qurilmada boshqa sotuvchi kirganda — sotuv o'z do'koniga yozilsin
    hint = to_int(data.get("shop_hint"), 0)
    if hint and hint != shop.pk:
        return Response({"detail": "Bu sotuv boshqa do'konniki — o'sha sotuvchi kirganda yuboriladi."},
                        status=409)
    discount = to_int(data.get("discount"), 0)
    rounding = to_int(data.get("rounding"), 0)
    if discount is None or rounding is None or discount < 0 or rounding < 0:
        return Response({"detail": "Chegirma/yaxlitlash noto'g'ri."}, status=400)
    payment_type = data.get("payment_type") or PaymentType.CASH
    if payment_type not in PaymentType.values:
        return Response({"detail": "Noma'lum to'lov turi."}, status=400)
    mode = data.get("mode") or SaleMode.QUICK
    if mode not in SaleMode.values:
        mode = SaleMode.QUICK

    client_ts = None
    if data.get("client_ts"):
        from django.utils.dateparse import parse_datetime

        try:
            client_ts = parse_datetime(str(data["client_ts"]))
        except (ValueError, TypeError):
            client_ts = None

    # Oflayn navbatdan kelgan sotuv: HAQIQIY vaqtiga yoziladi (yuborilgan kunga emas) va qoldiq
    # hisobda yetmasa ham qabul qilinadi — tovar qo'ldan ketib bo'lgan. Aks holda 23:50 dagi sotuv
    # ertangi kunga tushib, kechagi kun "kam savdo / kassa ortiqchasi" bo'lib chiqardi.
    data = request.data
    from datetime import timedelta

    offline = bool(data.get("offline"))
    if not offline:
        # Oflayn navbatdagi sotuv allaqachon bo'lib o'tgan — rad etilmaydi (yo'qolmasin); yangi sotuv esa
        # kechagi kun yakunlanmaguncha qabul qilinmaydi
        from .services.closing import pending_close_day, pending_message

        pending = pending_close_day(shop)
        if pending is not None:
            return Response({"detail": pending_message(pending), "redirect": "/kun-yakuni/"}, status=423)
    sold_at = None
    note = str(data.get("note") or "")
    if offline:
        now = timezone.now()
        if client_ts is not None and timezone.is_naive(client_ts):
            client_ts = timezone.make_aware(client_ts)
        mark = f"Oflayn sotuv — serverga {timezone.localtime(now):%d.%m %H:%M} da keldi"
        if client_ts is not None and now - timedelta(hours=48) <= client_ts <= now + timedelta(minutes=5):
            sold_at = min(client_ts, now)
        elif client_ts is not None:  # juda eski yoki kelajak — qabul vaqtiga, lekin iz qoladi
            mark += f"; qurilma vaqti {timezone.localtime(client_ts):%d.%m %H:%M}"
        note = (mark + (f" · {note}" if note else ""))[:200]

    from django.db import IntegrityError, transaction

    def _ok(s, code):
        from .public_views import receipt_url

        url = receipt_url(request, s)  # xaridorga QR chek manzili
        return Response(
            {"id": s.id, "total": s.total, "discount": s.discount, "rounding": s.rounding,
             "created_at": s.created_at.strftime("%H:%M"),
             "receipt_url": url, "receipt_qr": f"/chek/{s.public_code}/qr.svg",
             "receipt_code": s.public_code},
            status=code,
        )

    # Idempotentlik: offline navbatdan qayta kelgan sotuv dublikat yaratmaydi
    client_uid = str(data.get("client_uid") or "")[:64]
    if client_uid:
        existing = Sale.objects.filter(shop=shop, client_uid=client_uid).first()
        if existing:
            return _ok(existing, status.HTTP_200_OK)

    class _ZeroTotal(Exception):
        pass

    try:
        with transaction.atomic():
            sale = create_sale(
                shop=shop,
                seller=request.user,
                items=clean,
                discount=discount,
                rounding=rounding,
                payment_type=payment_type,
                is_wholesale=bool(data.get("is_wholesale", False)),
                mode=mode,
                client_ts=client_ts,
                note=note,
                client_uid=client_uid,
                sold_at=sold_at,
                allow_oversell=offline,
                debtor={"name": data.get("debtor_name"), "phone": data.get("debtor_phone"),
                        "due": data.get("debtor_due")},
            )
            if sale.total <= 0:
                raise _ZeroTotal  # nol summali chek bazada qolmasin (rollback)
            if sold_at is not None and timezone.localdate(sold_at) < timezone.localdate():
                # O'tgan kunga tushdi: yopilgan kassa va o'sha kun rostligi yangilansin
                from .services.sales import apply_late_sale

                day = timezone.localdate(sold_at)
                transaction.on_commit(lambda: apply_late_sale(shop, day))
    except (InsufficientStock, DebtorRequired, InvalidQuantity) as e:
        return Response({"detail": str(e)}, status=400)
    except _ZeroTotal:
        return Response({"detail": "Chek summasi 0 — sotuv qabul qilinmadi."}, status=400)
    except IntegrityError:
        # Bir vaqtda ikki marta keldi — birinchisi yozildi, o'shani qaytaramiz
        existing = Sale.objects.filter(shop=shop, client_uid=client_uid).first()
        if existing:
            return _ok(existing, status.HTTP_200_OK)
        raise
    # Real-time: sotuvdan keyin bugungi rostlikni yangilaymiz (throttled ~12s)
    try:
        from apps.analytics.scoring.services import refresh_today_if_stale

        refresh_today_if_stale()
    except Exception:  # noqa: BLE001 — sotuv javobi kechikmasin
        log.exception("Sotuvdan keyin rostlikni yangilash yiqildi")
    return _ok(sale, status.HTTP_201_CREATED)


@api_view(["GET"])
def product_lookup_api(request):
    """Skaner uchun: barkod yoki nom bo'yicha mahsulot qidirish (o'z do'koni)."""
    shop = _seller_shop(request)
    if shop is None:
        return Response([], status=200)
    from django.db.models import Q

    from apps.catalog.models import Product
    from apps.catalog.sizes import sorted_products

    def row(p):
        return {"id": p.id, "name": p.name, "price": p.sell_price, "unit": p.unit,
                "size": p.size, "stock": float(p.stock)}

    q = request.GET.get("q", "").strip()
    qs = Product.objects.filter(shop=shop, is_active=True)
    if q:
        exact = qs.filter(barcode=q).first()
        if exact:
            return Response([row(exact)])
        # "futbolka m" — har so'z nomda YOKI razmerga teng ("Futbolka — M" topiladi)
        for word in q.split()[:5]:
            qs = qs.filter(Q(name__icontains=word) | Q(size__iexact=word))
    # Razmerlar mantiqiy tartibda (XS < S < M, 36 < 37), keyin 20 tasi
    return Response([row(p) for p in sorted_products(qs[:80])[:20]])


@api_view(["GET"])
def today_summary_api(request):
    """Bugungi savdo yig'indisi (sotuvchi bosh sahifasi uchun)."""
    shop = _seller_shop(request)
    if shop is None:
        return Response({"detail": "Do'kon yo'q."}, status=400)
    today = timezone.localdate()
    from django.db.models import Count, Sum

    agg = Sale.objects.filter(shop=shop, **on_day("created_at", today)).aggregate(
        n=Count("id"), t=Sum("total"), d=Sum("discount"))
    return Response(
        {
            "date": str(today),
            "count": agg["n"],
            "total": agg["t"] or 0,
            "discount": agg["d"] or 0,
        }
    )
