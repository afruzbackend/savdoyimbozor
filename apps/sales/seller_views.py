"""Sotuvchi interfeysi ko'rinishlari."""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.catalog.models import Product, ProductCategory, Unit
from apps.core.format import som, to_dec, to_int
from apps.core.models import Notification, SystemSettings, notify

from .models import (
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
from .services import pricing


def _shop(request):
    return getattr(request.user, "shop", None)


def _dec(val, default="0"):
    try:
        return Decimal(str(val or default))
    except InvalidOperation:
        return Decimal(default)


def _gen_debt_notifications(user, shop):
    """Muddati kelgan (yoki o'tgan) nasiyalar uchun bildirishnoma yaratadi."""
    if shop is None:
        return
    today = timezone.localdate()
    due = Debt.objects.filter(shop=shop, is_paid=False, due_date__lte=today).exclude(due_date=None)
    for d in due:
        when = "bugun" if d.due_date == today else f"{d.due_date:%d.%m.%Y} (muddati o'tgan)"
        notify(
            user,
            Notification.Kind.DEBT_DUE,
            f"Nasiya qaytarish: {d.customer_name or 'xaridor'}",
            body=f"{som(d.amount)} so'm — {when}",
            url="/nasiya/",
            key=f"debt:{d.id}:{d.due_date}",
        )


@login_required
def notifications(request):
    """Sotuvchi bildirishnomalari ro'yxati."""
    shop = _shop(request)
    _gen_debt_notifications(request.user, shop)
    if request.method == "POST":
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return redirect("seller:notifications")
    items = list(request.user.notifications.all()[:100])
    return render(request, "seller/notifications.html", {"shop": shop, "items": items})


@login_required
def notification_open(request, pk):
    """Bildirishnomani ochish: o'qilgan deb belgilaydi va manziliga o'tadi."""
    n = get_object_or_404(request.user.notifications, pk=pk)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=["is_read"])
    return redirect(n.url or "seller:notifications")


@login_required
def home(request):
    shop = _shop(request)
    _gen_debt_notifications(request.user, shop)
    # Savdo bo'lmagan kun tushuntirilmagan bo'lsa — majburiy e'tirozga yo'naltiramiz
    if shop is not None and _pending_nosales(shop).exists():
        return redirect("seller:appeals")
    today = timezone.localdate()
    sales = Sale.objects.filter(shop=shop, created_at__date=today) if shop else Sale.objects.none()
    agg = sales.aggregate(total=Sum("total"), n=Count("id"))  # bitta so'rovda jami+soni
    low_stock = (
        list(
            Product.objects.filter(
                shop=shop,
                is_active=True,
                low_stock_threshold__gt=0,
                stock__lte=F("low_stock_threshold"),
            )[:5]
        )
        if shop
        else []
    )
    # Savdo yo'nalishi (meva/kiyim/...) bo'yicha tayyor katalog — dashboardда ko'rinsin
    trade_catalog, product_count = [], 0
    if shop is not None:
        product_count = Product.objects.filter(shop=shop, is_active=True).count()
        cat_qs = ProductCategory.objects.all()
        if shop.category_id:
            cat_qs = cat_qs.filter(shop_category=shop.category)
        trade_catalog = list(cat_qs.order_by("name")[:12])
    return render(
        request,
        "seller/home.html",
        {
            "shop": shop,
            "today_total": agg["total"] or 0,
            "today_count": agg["n"] or 0,
            "recent": sales.order_by("-created_at")[:8],
            "low_stock": low_stock,
            "trade_catalog": trade_catalog,   # shop yo'nalishiga mos mahsulot turlari
            "product_count": product_count,
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
    # Tayyor katalog: do'kon savdo turiga (shop_category) mos mahsulot toifalari
    catalog_qs = ProductCategory.objects.select_related("shop_category")
    if shop.category_id:
        catalog_qs = catalog_qs.filter(shop_category=shop.category)
    if not catalog_qs.exists():  # savdo turi biriktirilmagan bo'lsa — barchasi
        catalog_qs = ProductCategory.objects.all()
    catalog = list(catalog_qs.order_by("name"))

    if request.method == "POST":
        cat = ProductCategory.objects.filter(pk=request.POST.get("category") or 0).first()
        # Nom: katalog nomi + ixtiyoriy nav/rang (masalan "Olma — qizil")
        variant = request.POST.get("variant", "").strip()
        base_name = cat.name if cat else request.POST.get("name", "").strip()
        name = f"{base_name} — {variant}" if variant else base_name
        unit = request.POST.get("unit") or (cat.default_unit if cat else Unit.PIECE)
        if not name:
            messages.error(request, "Mahsulotni ro'yxatdan tanlang.")
            return redirect("seller:products")
        buy = to_int(request.POST.get("buy_price"), 0)
        sell = to_int(request.POST.get("sell_price"), 0)
        low = to_dec(request.POST.get("low_stock_threshold"), Decimal("0"))
        if buy is None or sell is None or buy < 0 or sell < 0 or low < 0:
            messages.error(request, "Narx va miqdor manfiy bo'lmasin.")
            return redirect("seller:products")
        if Product.objects.filter(shop=shop, name__iexact=name[:200], is_active=True).exists():
            messages.error(request, f"«{name}» allaqachon ro'yxatda bor — boshqa nav/rang yozing.")
            return redirect("seller:products")
        p = Product.objects.create(
            shop=shop,
            name=name[:200],
            category=cat,
            unit=unit,
            barcode=request.POST.get("barcode", "").strip()[:64],
            buy_price=buy,
            sell_price=sell,
            low_stock_threshold=low,
        )
        if not p.barcode:  # barkod berilmagan bo'lsa — avtomatik EAN-13
            from apps.catalog.barcodes import ensure_barcode

            ensure_barcode(p)
        messages.success(request, "Mahsulot qo'shildi.")
        return redirect("seller:products")
    catalog_json = [
        {"id": c.pk, "name": c.name, "unit": c.default_unit}
        for c in catalog
    ]
    from apps.core.pagination import paginate

    page = paginate(request, Product.objects.filter(shop=shop).order_by("name"), per_page=50)
    return render(
        request,
        "seller/products.html",
        {
            "shop": shop,
            "products": page.object_list,
            "page": page,
            "catalog": catalog,
            "catalog_json": catalog_json,  # json_script o'zi kodlaydi (ikki marta EMAS)
            "units": Unit.choices,
        },
    )


@login_required
def product_labels(request):
    """Barkod yorliqlari — chop etib mahsulotga yopishtirish (meva/kiyim/hammasi).

    Barkodsiz mahsulotlarga avtomatik EAN-13 beriladi.
    """
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    from apps.catalog.barcodes import ensure_barcodes_for_shop

    ensure_barcodes_for_shop(shop)
    products = Product.objects.filter(shop=shop, is_active=True).exclude(barcode="").order_by("name")
    return render(request, "seller/labels.html", {"shop": shop, "products": products})


@login_required
def stock_in(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        price = to_int(request.POST.get("unit_price"), 0)
        qty = to_dec(request.POST.get("quantity"))
        # Manfiy/nol kirim — foto/sababsiz yashirin "chiqarish" yo'li bo'lmasin
        if qty is None or qty <= 0:
            messages.error(request, "Miqdor 0 dan katta bo'lsin.")
            return redirect("seller:stock_in")
        if price is None or price < 0:
            messages.error(request, "Kelish narxi manfiy bo'lmasin.")
            return redirect("seller:stock_in")
        # 2 xil: mavjud mahsulotni tanlash YOKI qo'lda yangi nom yozish (yangi mahsulot yaratiladi)
        product = Product.objects.filter(pk=request.POST.get("product") or 0, shop=shop).first()
        if product is None:
            name = request.POST.get("new_name", "").strip()
            if not name:
                messages.error(request, "Mahsulotni tanlang yoki yangi nom kiriting.")
                return redirect("seller:stock_in")
            # Nom bo'yicha bor bo'lsa — o'shani olamiz, aks holda yangi yaratamiz
            product = Product.objects.filter(shop=shop, name__iexact=name).first()
            if product is None:
                product = Product.objects.create(
                    shop=shop,
                    name=name[:200],
                    unit=request.POST.get("unit", Unit.PIECE),
                    barcode=request.POST.get("barcode", "").strip()[:64],
                    buy_price=price,
                    sell_price=max(0, to_int(request.POST.get("sell_price"), 0) or 0),
                )
                if not product.barcode:
                    from apps.catalog.barcodes import ensure_barcode

                    ensure_barcode(product)
        in_packs = bool(request.POST.get("in_packs"))
        real_qty = qty * product.pack_coeff if in_packs else qty
        StockIn.objects.create(
            shop=shop,
            product=product,
            seller=request.user,
            quantity=qty,
            in_packs=in_packs,
            unit_price=price,
        )
        Product.objects.filter(pk=product.pk).update(stock=F("stock") + real_qty)
        messages.success(request, f"Kirim qo'shildi: {product.name} +{real_qty:g}")
        return redirect("seller:stock_in")
    return render(
        request,
        "seller/stock_in.html",
        {
            "shop": shop,
            "products": Product.objects.filter(shop=shop, is_active=True),
            "units": Unit.choices,
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
        # Sanalgan naqd MAJBURIY: bo'sh qolsa 0 deb yozilib, inspektorga noto'g'ri
        # "100% kamomad" signali ketardi.
        counted = to_int(request.POST.get("counted_cash"))
        if counted is None or counted < 0:
            messages.error(request, "Sandiqdagi sanalgan naqdni kiriting (0 bo'lsa 0 yozing).")
            return redirect("seller:daily_close")
        close, _ = DailyClose.objects.update_or_create(
            shop=shop, date=today, defaults={"seller": request.user}
        )
        close.lines.all().delete()
        computed = 0
        for p in prods:
            raw_ev = request.POST.get(f"evening_{p.id}")
            if raw_ev is None or str(raw_ev).strip() == "":
                continue  # sanalmagan mahsulot — 0 deb olinsa "hammasi sotilgan" bo'lardi
            morning = max(Decimal("0"), to_dec(request.POST.get(f"morning_{p.id}"), Decimal("0")))
            evening = max(Decimal("0"), to_dec(raw_ev, Decimal("0")))
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
        # Kassa (Z-hisobot) — kun yakunining majburiy qismi
        t = _register_totals(shop, today)
        RegisterClose.objects.update_or_create(
            shop=shop,
            date=today,
            defaults={
                "seller": request.user,
                "expected_cash": t["cash"],
                "counted_cash": counted,
                "card_total": t["card"],
                "transfer_total": t["transfer"],
                "checks_count": t["count"],
            },
        )
        diff = counted - t["cash"]
        note = ""
        if diff > 0:
            note = f" · Kassada ortiqcha: {som(diff)} so'm"
        elif diff < 0:
            note = f" · Kassada kamomad: {som(-diff)} so'm"
        messages.success(
            request,
            f"Kun yakunlandi. Hisoblangan: {som(computed)} · Kiritilgan: {som(entered)} so'm{note}",
        )
        return redirect("seller:daily_close")
    existing = DailyClose.objects.filter(shop=shop, date=today).first()
    reg = _register_totals(shop, today)
    today_close = RegisterClose.objects.filter(shop=shop, date=today).first()

    # "Ertalab" = kun BOSHIDAGI qoldiq. Joriy qoldiq emas — skaner sotuvlari uni kechgacha
    # allaqachon kamaytirgan bo'ladi (aks holda sotilgan ≈ 0 chiqib, nazorat ma'nosiz edi).
    # Avval kechagi kechki sanoq; bo'lmasa: joriy + bugun sotilgan − bugun kirim.
    yesterday = today - timedelta(days=1)
    y_evening = {
        ln.product_id: ln.evening_qty
        for ln in DailyCloseLine.objects.filter(
            close__shop=shop, close__date=yesterday, product__isnull=False
        )
    }
    sold_today = {
        r["product"]: r["q"]
        for r in SaleItem.objects.filter(
            sale__shop=shop, sale__created_at__date=today, product__isnull=False
        ).values("product").annotate(q=Sum("quantity"))
    }
    in_today = {
        r["product"]: r["q"]
        for r in StockIn.objects.filter(shop=shop, created_at__date=today)
        .values("product").annotate(q=Sum("quantity"))
    }
    lines_today = {}
    if existing:
        lines_today = {ln.product_id: ln for ln in existing.lines.all()}
    rows = []
    for p in prods:
        if p.id in lines_today:  # bugun allaqachon yopilgan — kiritilganini ko'rsatamiz
            morning = lines_today[p.id].morning_qty
            evening = lines_today[p.id].evening_qty
        else:
            morning = y_evening.get(p.id)
            if morning is None:
                morning = max(Decimal("0"), p.stock + (sold_today.get(p.id) or 0)
                              - (in_today.get(p.id) or 0))
            evening = None
        rows.append({"p": p, "morning": morning, "evening": evening})
    return render(
        request,
        "seller/daily_close.html",
        {
            "shop": shop,
            "products": prods,
            "rows": rows,
            "existing": existing,
            "reg": reg,
            "today_close": today_close,
        },
    )


@login_required
def returns(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        product = Product.objects.filter(pk=request.POST.get("product") or 0, shop=shop).first()
        qty = to_dec(request.POST.get("quantity"))
        reason = request.POST.get("reason", "").strip()[:200]
        amount = to_int(request.POST.get("amount"), 0)
        # Qoldiqni kamaytiradi — shuning uchun hisobdan chiqarish kabi nazorat qilinadi
        # (aks holda tovarni dalilsiz "qaytarish" deb chiqarib yuborish mumkin edi).
        if product is None:
            messages.error(request, "Mahsulotni tanlang.")
        elif qty is None or qty <= 0:
            messages.error(request, "Miqdor 0 dan katta bo'lsin.")
        elif qty > product.stock:
            messages.error(
                request,
                f"Qoldiqdan ko'p bo'lmasin: «{product.name}» qoldig'i {product.stock:g}, "
                f"so'ralgan {qty:g}.",
            )
        elif not reason:
            messages.error(request, "Sababni yozing — bu majburiy.")
        elif amount is None or amount < 0:
            messages.error(request, "Summa manfiy bo'lmasin.")
        else:
            if not amount:  # kiritilmagan bo'lsa — narx × miqdor
                amount = int(qty * product.sell_price)
            SaleReturn.objects.create(
                shop=shop, seller=request.user, product=product,
                quantity=qty, amount=amount, reason=reason,
            )
            Product.objects.filter(pk=product.pk).update(stock=F("stock") - qty)
            messages.success(request, "Qaytarish qayd etildi. Qoldiq yangilandi.")
        return redirect("seller:returns")
    return render(
        request,
        "seller/returns.html",
        {
            "shop": shop,
            "products": Product.objects.filter(shop=shop, is_active=True).order_by("name"),
            "recent": SaleReturn.objects.filter(shop=shop).select_related("product")[:10],
        },
    )


@login_required
def writeoff(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        product = Product.objects.filter(pk=request.POST.get("product") or 0, shop=shop).first()
        qty = to_dec(request.POST.get("quantity"), Decimal("0"))
        reason = request.POST.get("reason", "").strip()[:200]
        if product is None:
            messages.error(request, "Mahsulotni tanlang.")
        elif not reason:
            messages.error(request, "Sababni yozing — bu majburiy.")
        elif not request.FILES.get("photo"):
            messages.error(request, "Foto majburiy.")
        elif qty <= 0:
            messages.error(request, "Miqdorni to'g'ri kiriting.")
        elif qty > product.stock:
            messages.error(
                request,
                f"Qoldiqdan ko'p bo'lmasin: «{product.name}» qoldig'i {product.stock:g} "
                f"{product.get_unit_display()}, so'ralgan {qty:g}.",
            )
        else:
            WriteOff.objects.create(
                shop=shop, seller=request.user, product=product, product_name=product.name,
                quantity=qty, photo=request.FILES["photo"], reason=reason,
            )
            Product.objects.filter(pk=product.pk).update(stock=F("stock") - qty)
            messages.success(request, "Hisobdan chiqarish qayd etildi.")
        return redirect("seller:writeoff")
    return render(
        request,
        "seller/writeoff.html",
        {
            "shop": shop,
            "products": Product.objects.filter(shop=shop, is_active=True).order_by("name"),
            "recent": WriteOff.objects.filter(shop=shop).select_related("product")[:10],
        },
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
            from datetime import datetime

            due = None
            raw_due = request.POST.get("due_date", "").strip()
            if raw_due:
                for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        due = datetime.strptime(raw_due, fmt).date()
                        break
                    except ValueError:
                        continue
            name = request.POST.get("customer_name", "").strip()[:200]
            amount = to_int(request.POST.get("amount"))
            if not name:
                messages.error(request, "Xaridor ismini yozing.")
            elif amount is None or amount <= 0:
                messages.error(request, "Summa 0 dan katta bo'lsin.")
            else:
                Debt.objects.create(
                    shop=shop,
                    customer_name=name,
                    customer_phone=request.POST.get("customer_phone", "").strip()[:20],
                    amount=amount,
                    due_date=due,
                    note=request.POST.get("note", "").strip()[:200],
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
            "today": timezone.localdate(),
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
    # Foyda FAQAT tannarxi ma'lum mahsulotlar bo'yicha. Tez sotuvda (mahsulotsiz)
    # tannarx noma'lum — uni 0 deb olsak foyda = butun tushum bo'lib, chalg'itardi.
    known = [i for i in items if i.product_id and i.product and i.product.buy_price]
    profit = (
        sum(i.line_total - int(i.quantity * i.product.buy_price) for i in known) if known else None
    )

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
        # kg + dona + bog'lamni qo'shish ma'nosiz — qoldiqdagi mahsulot TURLARI soni
        "remaining": Product.objects.filter(shop=shop, is_active=True, stock__gt=0).count(),
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


def _register_totals(shop, day):
    """Kunlik kassa: to'lov turi bo'yicha jamlanma (Sale.payment_type asosida)."""
    from django.db.models import Count

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
    total = cash + card + transfer
    return {
        "cash": cash,
        "card": card,
        "transfer": transfer,
        "total": total,
        "count": count,
        "avg": int(total / count) if count else 0,
    }


@login_required
def register(request):
    """Kassa (POS): bugungi tushum to'lov turi bo'yicha + kunni yopish (Z-hisobot)."""
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    today = timezone.localdate()
    t = _register_totals(shop, today)

    if request.method == "POST":
        counted = to_int(request.POST.get("counted_cash"))
        if counted is None or counted < 0:
            messages.error(request, "Sandiqdagi sanalgan naqdni kiriting (0 bo'lsa 0 yozing).")
            return redirect("seller:register")
        note = request.POST.get("note", "").strip()[:200]
        prev = RegisterClose.objects.filter(shop=shop, date=today).first()
        if prev and prev.counted_cash != counted:
            # Qayta yopish — oldingi sanoq izsiz yo'qolmasin (inspektor ko'radi)
            note = (f"Qayta yopildi (avval {som(prev.counted_cash)}). " + note)[:200]
        RegisterClose.objects.update_or_create(
            shop=shop,
            date=today,
            defaults={
                "seller": request.user,
                "expected_cash": t["cash"],
                "counted_cash": counted,
                "card_total": t["card"],
                "transfer_total": t["transfer"],
                "checks_count": t["count"],
                "note": note,
            },
        )
        diff = counted - t["cash"]
        if diff == 0:
            messages.success(request, "Kassa yopildi. Naqd to'liq mos keldi.")
        elif diff < 0:
            messages.warning(request, f"Kassa yopildi. Kamomad: {som(-diff)} so'm.")
        else:
            messages.warning(request, f"Kassa yopildi. Ortiqcha: {som(diff)} so'm.")
        return redirect("seller:register")

    return render(
        request,
        "seller/register.html",
        {
            "shop": shop,
            "t": t,
            "today_close": RegisterClose.objects.filter(shop=shop, date=today).first(),
            "recent": Sale.objects.filter(shop=shop, created_at__date=today).order_by(
                "-created_at"
            )[:12],
        },
    )


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
        # Faqat BUGUNGI sotuv — eski (hisoblangan) kunlarni orqaga o'zgartirib bo'lmasin
        sale = get_object_or_404(
            Sale, pk=request.POST.get("sale") or 0, shop=shop, created_at__date=today
        )
        new_total = to_int(request.POST.get("new_total"), 0) or 0
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


def _pending_nosales(shop):
    """Tushuntirilmagan 'savdo yo'q' signallari (e'tiroz biriktirilmagan)."""
    from apps.analytics.models import Alert

    return (
        Alert.objects.filter(shop=shop, kind=Alert.Kind.ZERO_SALES, status=Alert.Status.NEW)
        .filter(appeals__isnull=True)
        .order_by("-date")
    )


@login_required
def appeals(request):
    """Sotuvchi e'tirozi + 'savdo yo'q' sabablarini tushuntirish."""
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    from apps.analytics.models import Alert, Appeal

    if request.method == "POST":
        alert_id = request.POST.get("nosales_alert")
        msg = request.POST.get("message", "").strip()
        if not msg:
            messages.error(request, "Matnni yozing — bo'sh yuborib bo'lmaydi.")
            return redirect("seller:appeals")
        if alert_id:  # nol-savdoni tushuntirish
            alert = Alert.objects.filter(
                pk=alert_id, shop=shop, kind=Alert.Kind.ZERO_SALES
            ).first()
            if alert and msg:
                Appeal.objects.create(
                    shop=shop, alert=alert, author=request.user, message=msg[:2000]
                )
                alert.status = Alert.Status.RESOLVED
                alert.save(update_fields=["status"])
                messages.success(request, "Izoh yuborildi. Rahmat.")
        elif msg:
            Appeal.objects.create(shop=shop, author=request.user, message=msg[:2000])
            messages.success(request, "E'tiroz yuborildi. Inspektor ko'rib chiqadi.")
        return redirect("seller:appeals")
    return render(
        request,
        "seller/appeals.html",
        {
            "shop": shop,
            "appeals": shop.appeals.select_related("author")[:30],
            "nosales": _pending_nosales(shop),
        },
    )


def _advice(latest):
    if not latest or not latest.has_data:
        return "Savdolarni muntazam kiriting — rostlik darajasi shundan hisoblanadi."
    weak = latest.weakest
    tips = {
        "cash": "Deklaratsiya (kassa) kiritilgan savdoga mos bo'lsin — har chekni kiriting.",
        "price": "Narxlaringiz bozor o'rtachasidan juda past ko'rinmoqda — real narxda soting.",
        "camera": "Kamera bahosi bilan farq bor — barcha xaridorlarga chek bering.",
        "stock": "Qoldiq hisobi savdoga mos emas — kun yakunini to'g'ri to'ldiring.",
    }
    return tips.get(weak, "Rostlik darajangiz yaxshi. Shu tarzda davom eting!")
