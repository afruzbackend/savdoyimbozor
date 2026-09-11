"""Sotuvchi interfeysi ko'rinishlari."""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.catalog.models import Product, ProductCategory, Unit
from apps.core.models import SystemSettings

from .models import DailyClose, DailyCloseLine, Debt, Sale, SaleItem, SaleReturn, StockIn, WriteOff
from .services import pricing


def _shop(request):
    return getattr(request.user, "shop", None)


def _dec(val, default="0"):
    try:
        return Decimal(str(val or default))
    except InvalidOperation:
        return Decimal(default)


@login_required
def home(request):
    shop = _shop(request)
    today = timezone.localdate()
    sales = Sale.objects.filter(shop=shop, created_at__date=today) if shop else Sale.objects.none()
    total = sum(s.total for s in sales)
    low_stock = (
        Product.objects.filter(
            shop=shop,
            is_active=True,
            low_stock_threshold__gt=0,
            stock__lte=F("low_stock_threshold"),
        )
        if shop
        else []
    )
    return render(
        request,
        "seller/home.html",
        {
            "shop": shop,
            "today_total": total,
            "today_count": sales.count(),
            "recent": sales.order_by("-created_at")[:8],
            "low_stock": low_stock[:5] if shop else [],
        },
    )


@login_required
def sale_screen(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    cfg = pricing.frontend_config(SystemSettings.get_solo())
    return render(request, "seller/sale.html", {"shop": shop, "pricing_config": json.dumps(cfg)})


@login_required
def scan_screen(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    cfg = pricing.frontend_config(SystemSettings.get_solo())
    return render(request, "seller/scan.html", {"shop": shop, "pricing_config": json.dumps(cfg)})


@login_required
def products(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        Product.objects.create(
            shop=shop,
            name=request.POST.get("name", "")[:200],
            category=ProductCategory.objects.filter(pk=request.POST.get("category") or 0).first(),
            unit=request.POST.get("unit", Unit.PIECE),
            barcode=request.POST.get("barcode", "")[:64],
            buy_price=int(request.POST.get("buy_price") or 0),
            sell_price=int(request.POST.get("sell_price") or 0),
            low_stock_threshold=_dec(request.POST.get("low_stock_threshold")),
        )
        messages.success(request, "Mahsulot qo'shildi.")
        return redirect("seller:products")
    return render(
        request,
        "seller/products.html",
        {
            "shop": shop,
            "products": Product.objects.filter(shop=shop).order_by("name"),
            "categories": ProductCategory.objects.all(),
            "units": Unit.choices,
        },
    )


@login_required
def stock_in(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        product = get_object_or_404(Product, pk=request.POST.get("product"), shop=shop)
        qty = _dec(request.POST.get("quantity"))
        in_packs = bool(request.POST.get("in_packs"))
        real_qty = qty * product.pack_coeff if in_packs else qty
        StockIn.objects.create(
            shop=shop,
            product=product,
            seller=request.user,
            quantity=qty,
            in_packs=in_packs,
            unit_price=int(request.POST.get("unit_price") or 0),
        )
        Product.objects.filter(pk=product.pk).update(stock=F("stock") + real_qty)
        messages.success(request, f"Kirim qo'shildi: {product.name} +{real_qty}")
        return redirect("seller:stock_in")
    return render(
        request,
        "seller/stock_in.html",
        {
            "shop": shop,
            "products": Product.objects.filter(shop=shop, is_active=True),
            "recent": StockIn.objects.filter(shop=shop).select_related("product")[:10],
        },
    )


@login_required
def daily_close(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    today = timezone.localdate()
    prods = Product.objects.filter(shop=shop, is_active=True)
    if request.method == "POST":
        close, _ = DailyClose.objects.update_or_create(
            shop=shop, date=today, defaults={"seller": request.user}
        )
        close.lines.all().delete()
        computed = 0
        for p in prods:
            morning = _dec(request.POST.get(f"morning_{p.id}"))
            evening = _dec(request.POST.get(f"evening_{p.id}"))
            sold = max(Decimal("0"), morning - evening)
            computed += int(sold * p.sell_price)
            DailyCloseLine.objects.create(
                close=close,
                product=p,
                product_name=p.name,
                morning_qty=morning,
                evening_qty=evening,
                unit_price=p.sell_price,
            )
        entered = (
            Sale.objects.filter(shop=shop, created_at__date=today).aggregate(s=Sum("total"))["s"]
            or 0
        )
        close.computed_sales = computed
        close.entered_sales = entered
        close.save()
        messages.success(
            request, f"Kun yakunlandi. Hisoblangan: {computed:,} · Kiritilgan: {entered:,} so'm"
        )
        return redirect("seller:daily_close")
    existing = DailyClose.objects.filter(shop=shop, date=today).first()
    return render(
        request, "seller/daily_close.html", {"shop": shop, "products": prods, "existing": existing}
    )


@login_required
def returns(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        SaleReturn.objects.create(
            shop=shop,
            seller=request.user,
            amount=int(request.POST.get("amount") or 0),
            reason=request.POST.get("reason", "")[:200],
        )
        messages.success(request, "Qaytarish qayd etildi.")
        return redirect("seller:returns")
    return render(
        request,
        "seller/returns.html",
        {"shop": shop, "recent": SaleReturn.objects.filter(shop=shop)[:10]},
    )


@login_required
def writeoff(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST" and request.FILES.get("photo"):
        WriteOff.objects.create(
            shop=shop,
            seller=request.user,
            product_name=request.POST.get("product_name", "")[:200],
            quantity=_dec(request.POST.get("quantity")),
            photo=request.FILES["photo"],
            reason=request.POST.get("reason", "")[:200],
        )
        messages.success(request, "Hisobdan chiqarish qayd etildi.")
        return redirect("seller:writeoff")
    return render(
        request,
        "seller/writeoff.html",
        {"shop": shop, "recent": WriteOff.objects.filter(shop=shop)[:10]},
    )


@login_required
def debts(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        if request.POST.get("pay"):
            debt = get_object_or_404(Debt, pk=request.POST["pay"], shop=shop)
            debt.is_paid = True
            debt.paid_at = timezone.now()
            debt.save(update_fields=["is_paid", "paid_at"])
            messages.success(request, "Nasiya to'landi deb belgilandi.")
        else:
            Debt.objects.create(
                shop=shop,
                customer_name=request.POST.get("customer_name", "")[:200],
                customer_phone=request.POST.get("customer_phone", "")[:20],
                amount=int(request.POST.get("amount") or 0),
                note=request.POST.get("note", "")[:200],
            )
            messages.success(request, "Nasiya qo'shildi.")
        return redirect("seller:debts")
    active = Debt.objects.filter(shop=shop, is_paid=False)
    return render(
        request,
        "seller/debts.html",
        {
            "shop": shop,
            "debts": active,
            "total": sum(d.amount for d in active),
            "paid": Debt.objects.filter(shop=shop, is_paid=True)[:10],
        },
    )


@login_required
def report(request):
    from apps.analytics.models import DailyScore

    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    today = timezone.localdate()
    start = today - timedelta(days=13)
    scores = list(DailyScore.objects.filter(shop=shop, date__range=(start, today)).order_by("date"))
    latest = scores[-1] if scores else None

    # Foyda (sotilgan mahsulot bo'yicha, taxminiy)
    items = SaleItem.objects.filter(
        sale__shop=shop, sale__created_at__date__range=(start, today)
    ).select_related("product")
    revenue = sum(i.line_total for i in items)
    cost = sum(int(i.quantity * (i.product.buy_price if i.product else 0)) for i in items)
    profit = revenue - cost

    chart = {
        "labels": [s.date.strftime("%d.%m") for s in scores],
        "truth": [s.truth_pct for s in scores],
        "entered": [s.entered_sales for s in scores],
    }

    # "Qanday oshiraman" maslahati — eng zaif qismga qarab
    advice = _advice(latest)

    part_labels = {
        "cash": "Kassa / deklaratsiya",
        "camera": "Kamera",
        "stock": "Qoldiq",
        "price": "Narx",
    }
    parts = []
    if latest:
        for k, lbl in part_labels.items():
            v = latest.parts.get(k)
            parts.append({"label": lbl, "value": v})

    return render(
        request,
        "seller/report.html",
        {
            "shop": shop,
            "latest": latest,
            "chart": chart,
            "parts": parts,
            "revenue": revenue,
            "profit": profit,
            "advice": advice,
        },
    )


def _advice(latest):
    if not latest:
        return "Savdolarni muntazam kiriting — rostlik darajasi shundan hisoblanadi."
    weak = latest.weakest
    tips = {
        "cash": "Deklaratsiya (kassa) kiritilgan savdoga mos bo'lsin — har chekni kiriting.",
        "price": "Narxlaringiz bozor o'rtachasidan juda past ko'rinmoqda — real narxda soting.",
        "camera": "Kamera bahosi bilan farq bor — barcha xaridorlarga chek bering.",
        "stock": "Qoldiq hisobi savdoga mos emas — kun yakunini to'g'ri to'ldiring.",
    }
    return tips.get(weak, "Rostlik darajangiz yaxshi. Shu tarzda davom eting!")
