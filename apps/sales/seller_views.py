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

from .models import (
    Correction,
    DailyClose,
    DailyCloseLine,
    Debt,
    Sale,
    SaleItem,
    SaleReturn,
    StockIn,
    WriteOff,
)
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

    # Davrlar bo'yicha ko'rsatkichlar
    from django.db.models import Sum

    sales_all = Sale.objects.filter(shop=shop)

    def _sum(qs):
        return qs.aggregate(s=Sum("total"))["s"] or 0

    metrics = {
        "today": _sum(sales_all.filter(created_at__date=today)),
        "week": _sum(sales_all.filter(created_at__date__gte=today - timedelta(days=6))),
        "month": _sum(sales_all.filter(created_at__date__gte=today - timedelta(days=29))),
        "total": _sum(sales_all),
        "discount": sales_all.aggregate(s=Sum("discount"))["s"] or 0,
        "count": sales_all.count(),
        "sold_qty": SaleItem.objects.filter(sale__shop=shop).aggregate(q=Sum("quantity"))["q"] or 0,
        "remaining": Product.objects.filter(shop=shop, is_active=True).aggregate(q=Sum("stock"))["q"]
        or 0,
    }

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
            "metrics": metrics,
        },
    )


@login_required
def rating(request):
    """Sotuvchi o'z do'koni bozorda nechanchi o'rinda ekanini ko'radi (boshqalar maxfiy)."""
    from django.db.models import Sum

    from apps.shops.models import Shop

    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    today = timezone.localdate()
    since = today - timedelta(days=29)

    def rank_within(shop_qs):
        rows = (
            Sale.objects.filter(shop__in=shop_qs, created_at__date__gte=since)
            .values("shop")
            .annotate(t=Sum("total"))
            .order_by("-t")
        )
        ordered = [r["shop"] for r in rows]
        total = shop_qs.count()
        pos = ordered.index(shop.id) + 1 if shop.id in ordered else total
        return pos, total

    market_shops = Shop.objects.filter(market=shop.market, is_active=True)
    overall_pos, overall_total = rank_within(market_shops)
    cat_shops = market_shops.filter(category=shop.category) if shop.category_id else market_shops
    cat_pos, cat_total = rank_within(cat_shops)

    my_sales = (
        Sale.objects.filter(shop=shop, created_at__date__gte=since).aggregate(s=Sum("total"))["s"]
        or 0
    )
    # Foizli pog'ona (top %)
    top_pct = round(overall_pos / overall_total * 100) if overall_total else 100

    # Mahsulot reytingi: har bir o'z mahsulotining bozordagi bir toifadagilar
    # orasida sotilish (miqdor) bo'yicha o'rni. FAQAT o'z mahsulotlari ko'rinadi.
    product_ranks = _product_ranks(shop, since)

    return render(
        request,
        "seller/rating.html",
        {
            "shop": shop,
            "overall_pos": overall_pos,
            "overall_total": overall_total,
            "cat_pos": cat_pos,
            "cat_total": cat_total,
            "cat_name": shop.category.name if shop.category_id else "",
            "my_sales": my_sales,
            "top_pct": top_pct,
            "product_ranks": product_ranks,
        },
    )


def _product_ranks(shop, since):
    """Har o'z mahsulotining bozordagi bir toifadagilar orasida sotilish o'rni."""
    from collections import defaultdict

    from django.db.models import Sum

    # Bozor bo'yicha mahsulotlar sotuvi (miqdor) — {product_id: qty}
    sold = {
        row["product"]: row["q"]
        for row in SaleItem.objects.filter(
            sale__shop__market=shop.market,
            sale__created_at__date__gte=since,
            product__isnull=False,
        )
        .values("product")
        .annotate(q=Sum("quantity"))
    }
    # Bozordagi mahsulotlar toifa bo'yicha guruhlanadi
    cat_products = defaultdict(list)  # category_id -> [(product_id, qty)]
    for mp in Product.objects.filter(
        shop__market=shop.market, category__isnull=False, is_active=True
    ).values("id", "category_id"):
        cat_products[mp["category_id"]].append((mp["id"], sold.get(mp["id"], 0)))

    ranks = []
    my_prods = Product.objects.filter(
        shop=shop, is_active=True, category__isnull=False
    ).select_related("category")
    for p in my_prods:
        qty = sold.get(p.id, 0)
        if not qty:
            continue  # sotilmagan mahsulot reytingda ko'rsatilmaydi
        ordered = [pid for pid, _ in sorted(cat_products[p.category_id], key=lambda x: -x[1])]
        pos = ordered.index(p.id) + 1 if p.id in ordered else len(ordered)
        ranks.append(
            {
                "name": p.name,
                "category": p.category.name,
                "pos": pos,
                "total": len(ordered),
                "qty": qty,
            }
        )
    ranks.sort(key=lambda r: r["pos"])
    return ranks[:10]


@login_required
def corrections(request):
    """Tuzatish: xato sotuv summasini o'chirmasdan tuzatish (eski qiymat saqlanadi).

    Yozuv hech qachon o'chmaydi — har tuzatish sabab bilan qayd etiladi va
    inspektor ko'radi. Bu soliqni yashirishning oldini oladi (izsiz o'zgarmaydi).
    """
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    today = timezone.localdate()

    if request.method == "POST":
        sale = get_object_or_404(Sale, pk=request.POST.get("sale"), shop=shop)
        new_total = int(request.POST.get("new_total") or 0)
        reason = request.POST.get("reason", "").strip()[:200]
        if new_total <= 0 or not reason:
            messages.error(request, "Yangi summa (0 dan katta) va sabab kiritilishi shart.")
        elif new_total == sale.total:
            messages.error(request, "Yangi summa eskisidan farq qilmaydi.")
        else:
            Correction.objects.create(
                shop=shop,
                user=request.user,
                target_model="Sale",
                target_id=sale.id,
                field="total",
                old_value=str(sale.total),
                new_value=str(new_total),
                reason=reason,
            )
            sale.total = new_total
            sale.note = (sale.note + " · Tuzatilgan").strip(" ·")[:200]
            sale.save(update_fields=["total", "note"])
            messages.success(request, "Tuzatish qayd etildi. Inspektor uni ko'radi.")
        return redirect("seller:corrections")

    return render(
        request,
        "seller/corrections.html",
        {
            "shop": shop,
            "sales": Sale.objects.filter(shop=shop, created_at__date=today).order_by("-created_at"),
            "history": Correction.objects.filter(shop=shop).select_related("user")[:30],
        },
    )


@login_required
def appeals(request):
    """Sotuvchi e'tirozi: signalga rozi bo'lmasa yozadi; inspektor javobini ko'radi."""
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    from apps.analytics.models import Appeal

    if request.method == "POST":
        msg = request.POST.get("message", "").strip()
        if msg:
            Appeal.objects.create(shop=shop, author=request.user, message=msg[:2000])
            messages.success(request, "E'tiroz yuborildi. Inspektor ko'rib chiqadi.")
        return redirect("seller:appeals")
    return render(
        request,
        "seller/appeals.html",
        {"shop": shop, "appeals": shop.appeals.select_related("author")[:30]},
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
