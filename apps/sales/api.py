"""Sotuvchi API'lari (API-first). Alpine frontend shu endpointlarni chaqiradi."""

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Sale
from .services.sales import InsufficientStock, create_sale


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
            "product_id": it.get("product_id") or None,
            "name": str(it.get("name") or "")[:200],
            "qty": qty,
            "unit_price": price,
        })
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

    from django.db import IntegrityError, transaction

    def _ok(s, code):
        return Response(
            {"id": s.id, "total": s.total, "discount": s.discount, "rounding": s.rounding,
             "created_at": s.created_at.strftime("%H:%M")},
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
                note=str(data.get("note") or ""),
                client_uid=client_uid,
            )
            if sale.total <= 0:
                raise _ZeroTotal  # nol summali chek bazada qolmasin (rollback)
    except InsufficientStock as e:
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
        pass
    return Response(
        {
            "id": sale.id,
            "total": sale.total,
            "discount": sale.discount,
            "rounding": sale.rounding,
            "created_at": sale.created_at.strftime("%H:%M"),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def product_lookup_api(request):
    """Skaner uchun: barkod yoki nom bo'yicha mahsulot qidirish (o'z do'koni)."""
    shop = _seller_shop(request)
    if shop is None:
        return Response([], status=200)
    from apps.catalog.models import Product

    q = request.GET.get("q", "").strip()
    qs = Product.objects.filter(shop=shop, is_active=True)
    if q:
        exact = qs.filter(barcode=q).first()
        if exact:
            return Response(
                [
                    {
                        "id": exact.id,
                        "name": exact.name,
                        "price": exact.sell_price,
                        "unit": exact.unit,
                    }
                ]
            )
        qs = qs.filter(name__icontains=q)
    data = [{"id": p.id, "name": p.name, "price": p.sell_price, "unit": p.unit} for p in qs[:20]]
    return Response(data)


@api_view(["GET"])
def today_summary_api(request):
    """Bugungi savdo yig'indisi (sotuvchi bosh sahifasi uchun)."""
    shop = _seller_shop(request)
    if shop is None:
        return Response({"detail": "Do'kon yo'q."}, status=400)
    today = timezone.localdate()
    qs = Sale.objects.filter(shop=shop, created_at__date=today)
    total = sum(s.total for s in qs)
    return Response(
        {
            "date": str(today),
            "count": qs.count(),
            "total": total,
            "discount": sum(s.discount for s in qs),
        }
    )
