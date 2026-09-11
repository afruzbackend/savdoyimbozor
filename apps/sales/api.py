"""Sotuvchi API'lari (API-first). Alpine frontend shu endpointlarni chaqiradi."""
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Sale
from .services import pricing
from .services.sales import create_sale


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
    if not items:
        return Response({"detail": "Kamida bitta mahsulot kerak."}, status=400)

    client_ts = None
    if data.get("client_ts"):
        from django.utils.dateparse import parse_datetime
        client_ts = parse_datetime(data["client_ts"])

    sale = create_sale(
        shop=shop, seller=request.user, items=items,
        discount=int(data.get("discount", 0)), rounding=int(data.get("rounding", 0)),
        payment_type=data.get("payment_type", "cash"),
        is_wholesale=bool(data.get("is_wholesale", False)),
        mode=data.get("mode", "quick"), client_ts=client_ts,
        note=data.get("note", ""),
    )
    return Response({
        "id": sale.id, "total": sale.total, "discount": sale.discount,
        "rounding": sale.rounding, "created_at": sale.created_at.strftime("%H:%M"),
    }, status=status.HTTP_201_CREATED)


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
            return Response([{"id": exact.id, "name": exact.name,
                              "price": exact.sell_price, "unit": exact.unit}])
        qs = qs.filter(name__icontains=q)
    data = [{"id": p.id, "name": p.name, "price": p.sell_price, "unit": p.unit}
            for p in qs[:20]]
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
    return Response({
        "date": str(today), "count": qs.count(), "total": total,
        "discount": sum(s.discount for s in qs),
    })
