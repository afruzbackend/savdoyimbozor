"""Xaridorga QR chek — ochiq sahifa (login shart emas, kod — yagona kalit).

Bozorda chek berilmaydi: xaridor QR'ni skanerlab, sotuvchi tizimga qancha yozganini ko'radi.
To'lagan summasi chekdagidan ko'p bo'lsa, bir bosishda xabar beradi → inspektorga signal.
Bu fiskal chek EMAS — savdo yozuvining xaridorga ko'rinadigan nusxasi.
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from apps.core.format import to_int
from apps.core.net import client_ip

from .models import Sale

CODE_LEN = 10


def _sale_or_404(code: str) -> Sale:
    code = (code or "").strip().upper()
    if len(code) != CODE_LEN or any(c not in Sale.CODE_ALPHABET for c in code):
        raise Http404
    try:
        return Sale.objects.select_related("shop", "shop__market").get(public_code=code)
    except Sale.DoesNotExist as e:
        raise Http404 from e


def receipt_url(request, sale: Sale) -> str:
    path = f"/chek/{sale.ensure_public_code()}/"
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}{path}" if base else request.build_absolute_uri(path)


def _can_report(sale) -> bool:
    limit = datetime.timedelta(days=settings.RECEIPT_REPORT_DAYS)
    return timezone.now() - sale.created_at <= limit and not hasattr(sale, "buyer_report")


def receipt(request, code):
    sale = _sale_or_404(code)
    items = list(sale.items.select_related("product"))
    # Sotuvchi summani keyin o'zgartirgan bo'lsa — xaridor ko'radi (dastlabki → hozirgi, sabab):
    # to'liq to'lagan xaridor darrov xabar bera oladi
    from .models import Correction

    corr = list(Correction.objects.filter(target_model="Sale", target_id=sale.pk, field="total")
                .order_by("created_at"))
    correction = ({"original": int(corr[0].old_value), "reason": corr[-1].reason,
                   "at": corr[-1].created_at} if corr and corr[0].old_value.isdigit() else None)
    return render(request, "receipt/public.html", {
        "sale": sale,
        "items": items,
        "correction": correction,
        "shop": sale.shop,
        "can_report": _can_report(sale),
        "reported": hasattr(sale, "buyer_report"),
        "sent": request.GET.get("sent") == "1",
        "report_days": settings.RECEIPT_REPORT_DAYS,
    })


@cache_control(public=True, max_age=86400)
def receipt_qr(request, code):
    """Chek manzilining QR kodi (SVG) — sotuvchi ekranida xaridorga ko'rsatiladi."""
    import qrcode
    import qrcode.image.svg

    sale = _sale_or_404(code)
    img = qrcode.make(receipt_url(request, sale), image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=10, border=2)
    return HttpResponse(img.to_string(), content_type="image/svg+xml")


@require_POST
def receipt_report(request, code):
    sale = _sale_or_404(code)
    back = f"/chek/{sale.public_code}/"
    if not _can_report(sale):
        return redirect(back)
    # Suiiste'moldan himoya: bitta manzildan soatiga 10 ta xabar
    key = f"receipt-report:{client_ip(request)}"
    if cache.get(key, 0) >= 10:
        return render(request, "receipt/public.html", {
            "sale": sale, "items": list(sale.items.select_related("product")), "shop": sale.shop,
            "can_report": False, "error": "Juda ko'p urinish — birozdan keyin qayta yuboring.",
        }, status=429)
    cache.set(key, cache.get(key, 0) + 1, 3600)

    paid = to_int(request.POST.get("paid_amount"))
    if paid is None or paid <= 0 or paid > max(sale.total * 20, 10_000_000):
        return render(request, "receipt/public.html", {
            "sale": sale, "items": list(sale.items.select_related("product")), "shop": sale.shop,
            "can_report": True, "error": "To'lagan summangizni to'g'ri yozing.",
            "report_days": settings.RECEIPT_REPORT_DAYS,
        }, status=400)
    from .services.receipts import file_buyer_report

    file_buyer_report(sale, paid, request.POST.get("comment", ""))
    return redirect(back + "?sent=1")
