"""Sotuvchi interfeysi ko'rinishlari."""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.catalog.models import Product, ProductCategory, Unit
from apps.catalog.sizes import product_order, size_key, sorted_products
from apps.core.dates import days_between, on_day, since_day
from apps.core.format import som, to_dec, to_int
from apps.core.models import SystemSettings

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


def _pk(value) -> int:
    """So'rovdan kelgan ID — raqam bo'lmasa 0 ("abc" bilan 500 xato bo'lmasin)."""
    return to_int(value, 0) or 0


def _photo_error(f):
    from django.core.exceptions import ValidationError

    from apps.core.media import validate_image_upload

    try:
        validate_image_upload(f)
    except ValidationError as e:
        return e.messages[0]
    return None


def _dec(val, default="0"):
    try:
        return Decimal(str(val or default))
    except InvalidOperation:
        return Decimal(default)


def _gen_debt_notifications(user, shop):
    """Nasiya eslatmalari: 1 kun OLDIN, o'sha KUNI va muddati o'tgan bo'lsa.

    Har bosqich bir marta (idempotent key). Sahifa ochilganda ishlaydi (Celery shart emas).
    """
    from .services.debts import debt_reminders

    debt_reminders(user, shop)


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
    sales = Sale.objects.filter(shop=shop, **on_day("created_at", today)) if shop else Sale.objects.none()
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
    # Savdo yo'nalishi (meva/kiyim/...) bo'yicha tayyor katalog — dashboardda ko'rinsin
    trade_catalog, product_count = [], 0
    if shop is not None:
        product_count = Product.objects.filter(shop=shop, is_active=True).count()
        cat_qs = ProductCategory.objects.all()
        if shop.category_id:
            cat_qs = cat_qs.filter(shop_category=shop.category)
        trade_catalog = list(cat_qs.order_by("name")[:12])
    # Kun boshi: maydalik hali kiritilmagan va sotuv yo'q — eslatamiz
    need_opening = False
    if shop is not None and not agg["n"]:
        from .models import CashOpen

        need_opening = not CashOpen.objects.filter(shop=shop, date=today).exists()
    # So'nggi sotuvlar: har biriga xaridor QR cheki (kod bo'lmasa bir marta yaratiladi)
    from .public_views import receipt_url

    recent = list(sales.order_by("-created_at")[:8]) if shop is not None else []
    for s in recent:
        s.receipt_link = receipt_url(request, s)
    return render(
        request,
        "seller/home.html",
        {
            "shop": shop,
            "need_opening": need_opening,
            "today_total": agg["total"] or 0,
            "today_count": agg["n"] or 0,
            "recent": recent,
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

    if request.method == "POST" and request.POST.get("action") in ("edit", "archive", "restore"):
        return _product_edit(request, shop)
    if request.method == "POST":
        cat = ProductCategory.objects.filter(pk=_pk(request.POST.get("category"))).first()
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
        if unit not in Unit.values:
            unit = Unit.PIECE
        # Variantlar (kiyim/poyabzal): o'lcham × rang — har biri alohida mahsulot (qoldiq, barkod)
        sizes = _clean_list(request.POST.getlist("sizes"), 20, upper=True)
        colors = _clean_list(request.POST.get("colors", "").replace(";", ",").split(","), 40)
        if sizes or colors:
            return _create_variants(request, shop, cat, name, unit, sizes or [""], colors or [""],
                                    buy, sell, low)
        if Product.objects.filter(shop=shop, name__iexact=name[:200], is_active=True).exists():
            messages.error(request, f"«{name}» allaqachon ro'yxatda bor — boshqa nav/rang yozing.")
            return redirect("seller:products")
        barcode = request.POST.get("barcode", "").strip()[:64]
        if barcode and Product.objects.filter(shop=shop, barcode=barcode, is_active=True).exists():
            messages.error(request, "Bu barkod boshqa mahsulotda bor — skaner adashmasin.")
            return redirect("seller:products")
        coeff = to_dec(request.POST.get("pack_coeff"), Decimal("1"))
        if coeff is None or coeff <= 0:
            coeff = Decimal("1")
        p = Product.objects.create(
            shop=shop,
            name=name[:200],
            category=cat,
            unit=unit,
            barcode=barcode,
            buy_price=buy,
            sell_price=sell,
            low_stock_threshold=low,
            pack_coeff=coeff,
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

    # Faollar avval, arxivdagilar oxirida; nom va o'lcham bo'yicha filtr
    qs = Product.objects.filter(shop=shop)
    q = (request.GET.get("q") or "").strip()
    size = (request.GET.get("size") or "").strip()
    if q:
        qs = qs.filter(name__icontains=q)
    if size:
        qs = qs.filter(size__iexact=size)
    page = paginate(request, sorted(qs, key=lambda p: (not p.is_active, product_order(p))), per_page=50)
    shop_sizes = sorted(
        set(Product.objects.filter(shop=shop, is_active=True).exclude(size="")
            .values_list("size", flat=True)),
        key=_size_key,
    )
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
            "q": q,
            "size": size,
            "shop_sizes": shop_sizes,
            "querystring": f"q={q}&size={size}",
            "size_presets": SIZE_PRESETS,
            # "Futbolka: M · 100, XL · 10" — model bo'yicha razmerlar qoldig'i (bir qarashda)
            "size_matrix": [m for m in _size_models(shop) if not q or q.lower() in m["base"].lower()],
        },
    )


# O'lcham tayyor to'plamlari (bir bosishda tanlash)
SIZE_PRESETS = {
    "Kiyim": ["XS", "S", "M", "L", "XL", "XXL", "3XL"],
    "Poyabzal": ["36", "37", "38", "39", "40", "41", "42", "43", "44", "45"],
    "Bolalar": ["92", "98", "104", "110", "116", "122", "128", "134", "140"],
}
# Razmer tartibi yagona manbada (apps/catalog/sizes.py) — sotuvchi va inspektor bir xil ko'radi
_size_key = size_key


def _clean_list(values, maxlen, upper=False):
    """Bo'shlarni olib tashlaydi, takrorlanmasin, tartib saqlanadi: ["M", " l ", "M"] → ["M", "L"]."""
    out = []
    for v in values:
        v = " ".join(str(v).split())[:maxlen]
        if upper:
            v = v.upper()
        if v and v.lower() not in {x.lower() for x in out}:
            out.append(v)
    return out[:30]


def _norm_size(size: str) -> str:
    """"xl" → "XL", " 36 " → "36" (harfli razmer katta harf bilan saqlanadi)."""
    size = " ".join(str(size).split())[:20]
    return size.upper() if size.isalpha() or size[:1].isdigit() and size[-2:].isalpha() else size


def _variant_for(shop, base, size, unit=Unit.PIECE, price=0):
    """Model + razmer → mavjud variant yoki shu modelning yangi varianti (toifa, birlik, sotish
    narxi, kam-qoldiq chegarasi qardosh razmerdan). Tez kirim va razmer jadvali shu yerdan."""
    from apps.catalog.barcodes import ensure_barcode

    size = _norm_size(size)
    p = Product.objects.filter(shop=shop, base_name__iexact=base, size__iexact=size,
                               is_active=True).first()
    if p is not None:
        return p
    sib = (Product.objects.filter(shop=shop, base_name__iexact=base).exclude(size="")
           .order_by("-is_active", "pk").first())
    p = Product.objects.create(
        shop=shop, name=f"{sib.base_name if sib else base} — {size}"[:200],
        base_name=(sib.base_name if sib else base)[:200], size=size,
        category=sib.category if sib else None, unit=sib.unit if sib else unit,
        buy_price=price or (sib.buy_price if sib else 0), sell_price=sib.sell_price if sib else 0,
        low_stock_threshold=sib.low_stock_threshold if sib else 0,
    )
    ensure_barcode(p)
    return p


def _create_variants(request, shop, cat, base, unit, sizes, colors, buy, sell, low):
    """Model × o'lcham × rang → alohida mahsulotlar (har biri o'z qoldig'i va barkodi bilan)."""
    from apps.catalog.barcodes import ensure_barcode

    created, skipped = 0, []
    for size in sizes:
        for color in colors:
            label = ", ".join(x for x in (size, color.lower() if color else "") if x)
            name = f"{base} — {label}"[:200]
            if Product.objects.filter(shop=shop, name__iexact=name, is_active=True).exists():
                skipped.append(label)
                continue
            p = Product.objects.create(
                shop=shop, name=name, base_name=base[:200], size=size, color=color,
                category=cat, unit=unit, buy_price=buy, sell_price=sell,
                low_stock_threshold=low,
            )
            ensure_barcode(p)
            created += 1
    if created:
        messages.success(request, f"«{base}»: {created} ta variant qo'shildi (har biriga barkod).")
    if skipped:
        messages.warning(request, "Allaqachon bor: " + ", ".join(skipped[:10]))
    return redirect("seller:products")


def _product_edit(request, shop):
    """Mahsulotni tahrirlash / arxivlash. Narx o'zgarishi tarixga (Correction) yoziladi —
    nazoratchi narx bilan o'ynashni ko'radi."""
    p = get_object_or_404(Product, pk=_pk(request.POST.get("id")), shop=shop)
    action = request.POST.get("action")
    if action in ("archive", "restore"):
        p.is_active = action == "restore"
        p.save(update_fields=["is_active"])
        messages.success(
            request, f"«{p.name}» " + ("qayta faollashtirildi." if p.is_active else "arxivlandi.")
        )
        return redirect("seller:products")
    buy = to_int(request.POST.get("buy_price"))
    sell = to_int(request.POST.get("sell_price"))
    low = to_dec(request.POST.get("low_stock_threshold"), Decimal("0"))
    coeff = to_dec(request.POST.get("pack_coeff"), Decimal("1"))
    barcode = request.POST.get("barcode", "").strip()[:64]
    if buy is None or sell is None or buy < 0 or sell < 0 or low is None or low < 0:
        messages.error(request, "Narx va miqdor manfiy bo'lmasin.")
        return redirect("seller:products")
    if coeff is None or coeff <= 0:
        messages.error(request, "Qop koeffitsiyenti 0 dan katta bo'lsin.")
        return redirect("seller:products")
    if barcode and Product.objects.filter(
        shop=shop, barcode=barcode, is_active=True
    ).exclude(pk=p.pk).exists():
        messages.error(request, "Bu barkod boshqa mahsulotda bor — skaner adashmasin.")
        return redirect("seller:products")
    for field, new in (("sell_price", sell), ("buy_price", buy)):
        old = getattr(p, field)
        if old != new:
            Correction.objects.create(
                shop=shop, user=request.user, target_model="Product", target_id=p.pk,
                field=field, old_value=str(old), new_value=str(new),
                reason=f"«{p.name}» narxi o'zgardi"[:200],
            )
    p.buy_price, p.sell_price = buy, sell
    p.low_stock_threshold, p.pack_coeff = low, coeff
    if barcode:
        p.barcode = barcode
    p.save(update_fields=["buy_price", "sell_price", "low_stock_threshold", "pack_coeff",
                          "barcode"])
    messages.success(request, f"«{p.name}» saqlandi.")
    return redirect("seller:products")


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
    products = sorted_products(Product.objects.filter(shop=shop, is_active=True).exclude(barcode=""))
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
        product = Product.objects.filter(pk=_pk(request.POST.get("product")), shop=shop).first()
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
        # Kirim DALILI: katta kirimga nakladnoy fotosi majburiy (kompensatsiya kutilganda
        # kirimni oshirib yozishning oldini oladi); yetkazib beruvchi yoziladi
        supplier = request.POST.get("supplier_name", "").strip()[:200]
        supplier_stir = "".join(c for c in request.POST.get("supplier_stir", "") if c.isdigit())[:15]
        photo = request.FILES.get("invoice_photo")
        total = int(real_qty * price)
        min_photo = SystemSettings.get_solo().stockin_photo_min
        if photo is not None:
            err = _photo_error(photo)
            if err:
                messages.error(request, err)
                return redirect("seller:stock_in")
        elif min_photo and total >= min_photo:
            messages.error(
                request,
                f"Kirim summasi {som(total)} so'm — {som(min_photo)} so'mdan katta kirimga "
                "nakladnoy (yuk xati) fotosi majburiy.",
            )
            return redirect("seller:stock_in")
        from .models import StockMove
        from .services.stock import record_move

        with transaction.atomic():
            si = StockIn.objects.create(
                shop=shop,
                product=product,
                seller=request.user,
                quantity=qty,
                in_packs=in_packs,
                unit_price=price,
                supplier_name=supplier,
                supplier_stir=supplier_stir,
                invoice_photo=photo or "",
            )
            record_move(product, StockMove.Kind.IN, delta=real_qty, ref=f"StockIn#{si.pk}",
                        user=request.user)
        messages.success(request, f"Kirim qo'shildi: {product.name} +{real_qty:g}")
        return redirect("seller:stock_in")
    return render(
        request,
        "seller/stock_in.html",
        {
            "shop": shop,
            "products": sorted_products(Product.objects.filter(shop=shop, is_active=True)),
            "units": Unit.choices,
            "recent": StockIn.objects.filter(shop=shop).select_related("product")
            .order_by("-created_at")[:10],
            "photo_min": SystemSettings.get_solo().stockin_photo_min,
            "size_models": _size_models(shop),
        },
    )


def _size_models(shop) -> list[dict]:
    """Razmerli modellar (kirim jadvali uchun): [{base, unit, buy_price, sizes:[{label, product_id, stock}]}]."""
    groups = {}
    for p in Product.objects.filter(shop=shop, is_active=True).exclude(size="").order_by("pk"):
        groups.setdefault(p.base_name or p.name.split(" — ")[0], []).append(p)
    out = []
    for base, ps in sorted(groups.items(), key=lambda x: x[0].lower()):
        ps.sort(key=lambda p: (_size_key(p.size), p.color))
        out.append({
            "base": base, "unit": ps[0].unit, "buy_price": ps[0].buy_price,
            "sizes": [{"size": p.size, "label": p.size + (f", {p.color.lower()}" if p.color else ""),
                       "product_id": p.pk, "stock": float(p.stock),
                       "state": "zero" if p.stock <= 0 else ("low" if p.is_low_stock else "")}
                      for p in ps],
            "total": float(sum(p.stock for p in ps)),
        })
    return out


@login_required
def stock_in_quick_parse(request):
    """Tez kirim: matn (ovozdan yoki yozilgan) → taklif qatorlar (JSON). Bazaga yozmaydi."""
    from django.http import JsonResponse

    from .services.quick_entry import parse

    shop = _shop(request)
    if shop is None or request.method != "POST":
        return JsonResponse({"rows": []}, status=400)
    try:
        text = json.loads(request.body or "{}").get("text", "")
    except (ValueError, AttributeError):
        text = ""
    text = str(text)[:2000]
    return JsonResponse({"rows": parse(text, Product.objects.filter(shop=shop, is_active=True))})


@login_required
def stock_in_quick_save(request):
    """Tasdiqlangan tez kirim qatorlari — bitta tranzaksiyada, bitta nakladnoy bilan."""
    shop = _shop(request)
    if shop is None or request.method != "POST":
        return redirect("seller:stock_in")
    try:
        rows = json.loads(request.POST.get("rows") or "[]")
    except ValueError:
        rows = []
    if not isinstance(rows, list) or not rows or len(rows) > 50:
        messages.error(request, "Kirim qatorlari yo'q.")
        return redirect("seller:stock_in")
    valid_units = set(Unit.values)
    plan = []
    for n, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            continue
        qty = to_dec(r.get("qty"))
        price = to_int(r.get("price"), 0)
        if qty is None or qty <= 0 or price is None or price < 0:
            messages.error(request, f"{n}-qator: miqdor/narx noto'g'ri.")
            return redirect("seller:stock_in")
        product = None
        if r.get("product_id"):
            product = Product.objects.filter(pk=_pk(r["product_id"]), shop=shop).first()
            if product is None:
                messages.error(request, f"{n}-qator: mahsulot topilmadi.")
                return redirect("seller:stock_in")
        name = str(r.get("product_name") or "").strip()[:200]
        if product is None and not name:
            messages.error(request, f"{n}-qator: mahsulot nomi yo'q.")
            return redirect("seller:stock_in")
        unit = r.get("unit") if r.get("unit") in valid_units else Unit.PIECE
        # Razmer (variant): model + razmer — yangi razmer shu modelning varianti bo'lib yaratiladi
        variant = None
        if product is None and str(r.get("size") or "").strip():
            base = str(r.get("base_name") or name.split(" — ")[0]).strip()[:200]
            variant = (base, str(r["size"]).strip()[:20])
        plan.append((product, name, unit, qty, price, bool(r.get("in_packs")), variant))

    supplier = request.POST.get("supplier_name", "").strip()[:200]
    supplier_stir = "".join(c for c in request.POST.get("supplier_stir", "") if c.isdigit())[:15]
    photo = request.FILES.get("invoice_photo")

    def coeff(product, packs):
        return (product.pack_coeff if product and packs and (product.pack_coeff or 1) > 1 else 1)

    total = sum(int(q * coeff(p, pk) * pr) for p, _n, _u, q, pr, pk, _v in plan)
    min_photo = SystemSettings.get_solo().stockin_photo_min
    if photo is not None:
        err = _photo_error(photo)
        if err:
            messages.error(request, err)
            return redirect("seller:stock_in")
    elif min_photo and total >= min_photo:
        messages.error(request, f"Kirim jami {som(total)} so'm — {som(min_photo)} so'mdan katta "
                                "kirimga nakladnoy (yuk xati) fotosi majburiy.")
        return redirect("seller:stock_in")

    from .models import StockMove
    from .services.stock import record_move

    saved_photo = ""
    with transaction.atomic():
        for product, name, unit, qty, price, packs, variant in plan:
            if product is None and variant:
                product = _variant_for(shop, variant[0], variant[1], unit, price)
            if product is None:
                product = Product.objects.filter(shop=shop, name__iexact=name).first()
            if product is None:
                product = Product.objects.create(shop=shop, name=name, unit=unit, buy_price=price)
                from apps.catalog.barcodes import ensure_barcode

                ensure_barcode(product)
            in_packs = packs and (product.pack_coeff or 1) > 1
            real_qty = qty * product.pack_coeff if in_packs else qty
            si = StockIn(shop=shop, product=product, seller=request.user, quantity=qty,
                         in_packs=in_packs, unit_price=price, supplier_name=supplier,
                         supplier_stir=supplier_stir, source="quick")
            if photo is not None and not saved_photo:
                si.invoice_photo = photo  # bitta nakladnoy — birinchi qatorga yuklanadi
            elif saved_photo:
                si.invoice_photo.name = saved_photo  # qolganlari o'sha faylga ishora qiladi
            si.save()
            saved_photo = saved_photo or (si.invoice_photo.name or "")
            record_move(product, StockMove.Kind.IN, delta=real_qty, ref=f"StockIn#{si.pk}",
                        user=request.user)
    request.audit_detail = f"Tez kirim: {len(plan)} qator, {som(total)} so'm"
    messages.success(request, f"Kirim qo'shildi: {len(plan)} ta mahsulot, jami {som(total)} so'm.")
    return redirect("seller:stock_in")


def _morning_baselines(shop, today, prods, mv, existing):
    """Har mahsulot uchun kun boshi qoldig'i: {pid: (miqdor, qulflanganmi)}.

    Tartib: bugungi saqlangan sanoq > kechagi kechki sanoq > tizim hisobi.
    Kechagi sanoq bo'lsa ertalabni sotuvchi O'ZGARTIRA OLMAYDI — aks holda ertalabni
    kechqurunga tenglab "hech narsa sotilmadi" deb qoldiq nazoratini chetlab o'tish mumkin edi.
    """
    from .services.stock import system_morning

    yesterday = today - timedelta(days=1)
    y_evening = {
        ln.product_id: ln.evening_qty
        for ln in DailyCloseLine.objects.filter(
            close__shop=shop, close__date=yesterday, product__isnull=False
        )
    }
    saved = {ln.product_id: ln.morning_qty for ln in existing.lines.all()} if existing else {}
    out = {}
    for p in prods:
        if p.id in saved:
            out[p.id] = (saved[p.id], True)
        elif p.id in y_evening:
            out[p.id] = (y_evening[p.id], True)
        else:
            out[p.id] = (system_morning(p, mv), False)  # birinchi sanoq — tuzatish mumkin
    return out


@login_required
def daily_close(request):
    from .services.stock import day_movements, sold_qty

    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    today = timezone.localdate()
    prods = sorted_products(Product.objects.filter(shop=shop, is_active=True))
    existing = DailyClose.objects.filter(shop=shop, date=today).first()
    mv = day_movements(shop, today)
    base = _morning_baselines(shop, today, prods, mv, existing)
    if request.method == "POST":
        # Sanalgan naqd MAJBURIY: bo'sh qolsa 0 deb yozilib, inspektorga noto'g'ri
        # "100% kamomad" signali ketardi.
        counted = to_int(request.POST.get("counted_cash"))
        if counted is None or counted < 0:
            messages.error(request, "Sandiqdagi sanalgan naqdni kiriting (0 bo'lsa 0 yozing).")
            return redirect("seller:daily_close")
        # Rasta fotosi — qoldiqning ko'rinadigan dalili (yong'in/kompensatsiya). Mahsulot
        # sanalgan bo'lsa majburiy; qayta yopishda eski foto qoladi (yangisi ixtiyoriy)
        photo = request.FILES.get("photo")
        any_counted = any(
            str(request.POST.get(f"evening_{p.id}") or "").strip() for p in prods
        )
        if photo is not None:
            err = _photo_error(photo)
            if err:
                messages.error(request, err)
                return redirect("seller:daily_close")
        elif any_counted and not (existing and existing.photo):
            messages.error(request, "Rastani suratga oling — kun yakuni fotosi majburiy.")
            return redirect("seller:daily_close")
        from .services.cash import close_register

        with transaction.atomic():
            close, _ = DailyClose.objects.update_or_create(
                shop=shop, date=today, defaults={"seller": request.user}
            )
            close.lines.all().delete()
            computed = 0
            for p in prods:
                raw_ev = request.POST.get(f"evening_{p.id}")
                if raw_ev is None or str(raw_ev).strip() == "":
                    continue  # sanalmagan mahsulot — 0 deb olinsa "hammasi sotilgan" bo'lardi
                evening = to_dec(raw_ev)
                if evening is None or evening < 0:
                    continue
                morning, locked = base[p.id]
                if not locked:
                    posted = to_dec(request.POST.get(f"morning_{p.id}"))
                    if posted is not None and posted >= 0:
                        morning = posted
                computed += int(sold_qty(morning, evening, p.id, mv) * p.sell_price)
                DailyCloseLine.objects.create(
                    close=close,
                    product=p,
                    product_name=p.name,
                    morning_qty=morning,
                    evening_qty=evening,
                    unit_price=p.sell_price,
                )
                # Sanoq = haqiqat: tizim qoldig'i jismoniy sanoqqa tenglashadi (jurnalda "sanoq")
                # (tez sotuv mahsulotga bog'lanmaydi — aks holda qoldiq cheksiz o'sardi)
                from .models import StockMove
                from .services.stock import record_move

                record_move(p, StockMove.Kind.COUNT, set_to=evening, ref=f"DailyClose#{close.pk}",
                            user=request.user)
            entered = (
                Sale.objects.filter(shop=shop, **on_day("created_at", today)).aggregate(s=Sum("total"))[
                    "s"
                ]
                or 0
            )
            close.computed_sales = computed
            close.entered_sales = entered
            if photo is not None:
                close.photo = photo
            close.save()
        # Kassa (Z-hisobot) — kun yakunining majburiy qismi (maydalik + nasiya qaytishi hisobda)
        _z, diff = close_register(
            shop, today, counted, request.user, note=request.POST.get("cash_note", "")
        )
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

    from .services.cash import register_totals

    reg = register_totals(shop, today)
    today_close = RegisterClose.objects.filter(shop=shop, date=today).first()
    lines_today = {ln.product_id: ln for ln in existing.lines.all()} if existing else {}
    rows = []
    for p in prods:
        morning, locked = base[p.id]
        delta = mv["in"][p.id] - mv["out"][p.id]
        evening = lines_today[p.id].evening_qty if p.id in lines_today else None
        rows.append({"p": p, "morning": morning, "locked": locked, "delta": delta,
                     "evening": evening})
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
        product = Product.objects.filter(pk=_pk(request.POST.get("product")), shop=shop).first()
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
            from .models import StockMove
            from .services.stock import NegativeStock, record_move

            try:
                with transaction.atomic():
                    ret = SaleReturn.objects.create(
                        shop=shop, seller=request.user, product=product,
                        quantity=qty, amount=amount, reason=reason,
                    )
                    # Qulf ostida qayta tekshiriladi — parallel so'rov qoldiqdan oshirmasin
                    record_move(product, StockMove.Kind.RETURN, delta=-qty,
                                ref=f"Return#{ret.pk}", user=request.user, allow_negative=False)
            except NegativeStock:
                messages.error(request, "Qoldiq o'zgardi — qayta urinib ko'ring.")
                return redirect("seller:returns")
            messages.success(request, "Qaytarish qayd etildi. Qoldiq yangilandi.")
        return redirect("seller:returns")
    return render(
        request,
        "seller/returns.html",
        {
            "shop": shop,
            "products": sorted_products(Product.objects.filter(shop=shop, is_active=True)),
            "recent": SaleReturn.objects.filter(shop=shop).select_related("product")[:10],
        },
    )


@login_required
def writeoff(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        product = Product.objects.filter(pk=_pk(request.POST.get("product")), shop=shop).first()
        qty = to_dec(request.POST.get("quantity"), Decimal("0"))
        reason = request.POST.get("reason", "").strip()[:200]
        if product is None:
            messages.error(request, "Mahsulotni tanlang.")
        elif not reason:
            messages.error(request, "Sababni yozing — bu majburiy.")
        elif not request.FILES.get("photo"):
            messages.error(request, "Foto majburiy.")
        elif (photo_err := _photo_error(request.FILES["photo"])):
            messages.error(request, photo_err)
        elif qty <= 0:
            messages.error(request, "Miqdorni to'g'ri kiriting.")
        elif qty > product.stock:
            messages.error(
                request,
                f"Qoldiqdan ko'p bo'lmasin: «{product.name}» qoldig'i {product.stock:g} "
                f"{product.get_unit_display()}, so'ralgan {qty:g}.",
            )
        else:
            from .models import StockMove
            from .services.stock import NegativeStock, record_move

            try:
                with transaction.atomic():
                    wo = WriteOff.objects.create(
                        shop=shop, seller=request.user, product=product,
                        product_name=product.name, quantity=qty, photo=request.FILES["photo"],
                        reason=reason,
                    )
                    # Qulf ostida qayta tekshiriladi — parallel so'rov qoldiqdan oshirmasin
                    record_move(product, StockMove.Kind.WRITEOFF, delta=-qty,
                                ref=f"WriteOff#{wo.pk}", user=request.user, allow_negative=False)
            except NegativeStock:
                messages.error(request, "Qoldiq o'zgardi — qayta urinib ko'ring.")
                return redirect("seller:writeoff")
            messages.success(request, "Hisobdan chiqarish qayd etildi.")
        return redirect("seller:writeoff")
    return render(
        request,
        "seller/writeoff.html",
        {
            "shop": shop,
            "products": sorted_products(Product.objects.filter(shop=shop, is_active=True)),
            "recent": WriteOff.objects.filter(shop=shop).select_related("product")[:10],
        },
    )


@login_required
def debts(request):
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    if request.method == "POST":
        if request.POST.get("sms_toggle"):
            debt = get_object_or_404(Debt, pk=_pk(request.POST["sms_toggle"]), shop=shop)
            debt.sms_remind = not debt.sms_remind
            debt.save(update_fields=["sms_remind"])
            state = "yoqildi" if debt.sms_remind else "o'chirildi"
            messages.success(request, f"{debt.customer_name}: SMS eslatma {state}.")
            return redirect("seller:debts")
        if request.POST.get("extend"):
            # Xaridor muddat so'radi — yangi sana (eslatmalar yangi sanaga qayta keladi)
            from .services.debts import parse_due

            debt = get_object_or_404(Debt, pk=_pk(request.POST["extend"]), shop=shop, is_paid=False)
            due = parse_due(request.POST.get("due_date"))
            if due is None or due < timezone.localdate():
                messages.error(request, "Yangi qaytarish sanasini tanlang (bugun yoki keyin).")
            else:
                old = debt.due_date
                debt.due_date = due
                debt.note = (debt.note + f" · muddat {old:%d.%m}→{due:%d.%m}" if old else debt.note)[:200]
                debt.save(update_fields=["due_date", "note"])
                messages.success(request, f"{debt.customer_name}: yangi muddat {due:%d.%m.%Y}.")
            return redirect("seller:debts")
        if request.POST.get("pay"):
            # To'lov (qisman ham): naqd to'lov bugungi kassadagi kutilgan naqdga qo'shiladi
            from .services.cash import CashError, pay_debt

            debt = get_object_or_404(Debt, pk=_pk(request.POST["pay"]), shop=shop)
            amount = to_int(request.POST.get("amount"))
            if amount is None:
                amount = debt.remaining  # summa yozilmasa — to'liq
            try:
                pay_debt(debt, amount, request.POST.get("method", "cash"), request.user)
                debt.refresh_from_db()
                if debt.is_paid:
                    messages.success(request, f"{debt.customer_name}: nasiya to'liq yopildi.")
                else:
                    messages.success(
                        request,
                        f"{debt.customer_name}: {som(amount)} so'm qabul qilindi, "
                        f"qoldiq {som(debt.remaining)} so'm.",
                    )
            except CashError as e:
                messages.error(request, str(e))
        else:
            from .services.debts import parse_due

            due = parse_due(request.POST.get("due_date"))
            name = request.POST.get("customer_name", "").strip()[:200]
            amount = to_int(request.POST.get("amount"))
            if not name:
                messages.error(request, "Xaridor ismini yozing.")
            elif amount is None or amount <= 0:
                messages.error(request, "Summa 0 dan katta bo'lsin.")
            elif due is None:
                # Qaytarish sanasi MAJBURIY — shunda bir kun oldin va o'sha kuni eslatiladi
                messages.error(request, "Qaytarish sanasini tanlang.")
            elif due < timezone.localdate():
                messages.error(request, "Qaytarish sanasi o'tgan kun bo'lmasin.")
            else:
                Debt.objects.create(
                    shop=shop,
                    customer_name=name,
                    customer_phone=request.POST.get("customer_phone", "").strip()[:20],
                    amount=amount,
                    due_date=due,
                    note=request.POST.get("note", "").strip()[:200],
                    sms_remind=request.POST.get("sms_remind") == "on",
                )
                messages.success(request, "Nasiya qo'shildi.")
        return redirect("seller:debts")
    active = list(Debt.objects.filter(shop=shop, is_paid=False).order_by("due_date", "created_at"))
    from apps.core import sms
    from apps.core.models import SmsMessage

    from .models import DebtPayment

    # Har nasiyaning oxirgi SMS holati (1 so'rov)
    last_sms = {}
    for m in SmsMessage.objects.filter(
        key__regex=r"^debt:(" + "|".join(str(d.pk) for d in active) + r"):"
    ).order_by("created_at") if active else []:
        last_sms[int(m.key.split(":")[1])] = m
    for d in active:
        d.last_sms = last_sms.get(d.pk)

    return render(
        request,
        "seller/debts.html",
        {
            "shop": shop,
            "debts": active,
            "total": sum(d.remaining for d in active),
            "tomorrow": timezone.localdate() + timedelta(days=1),
            "payments": DebtPayment.objects.filter(shop=shop)
            .select_related("debt").order_by("-created_at")[:15],
            "today": timezone.localdate(),
            "sms_on": sms.enabled(),
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
        sale__shop=shop, **days_between("sale__created_at", start, today)
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
        "today": _sum(sales_all.filter(**on_day("created_at", today))),
        "week": _sum(sales_all.filter(**since_day("created_at", today - timedelta(days=6)))),
        "month": _sum(sales_all.filter(**since_day("created_at", today - timedelta(days=29)))),
        "total": _sum(sales_all),
        "discount": sales_all.aggregate(s=Sum("discount"))["s"] or 0,
        "count": sales_all.count(),
        "sold_qty": SaleItem.objects.filter(sale__shop=shop).aggregate(q=Sum("quantity"))["q"] or 0,
        # kg + dona + bog'lamni qo'shish ma'nosiz — qoldiqdagi mahsulot TURLARI soni
        "remaining": Product.objects.filter(shop=shop, is_active=True, stock__gt=0).count(),
    }

    chart = {
        "labels": [s.date.strftime("%d.%m") for s in scores],
        "truth": [s.truth_pct if s.measured else None for s in scores],
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


RATING_CACHE_SECONDS = 600  # reyting 10 daqiqada bir yangilanadi


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

    # Bozor bo'yicha 30 kunlik savdo — BITTA so'rov, 10 daqiqa kesh (reyting soniyada o'zgarmaydi,
    # bozordagi yuzlab sotuvchi sahifani ochganda har biri butun bozorni qayta yig'masin)
    from django.core.cache import cache

    key = f"rating:shops:{shop.market_id}:{since.isoformat()}"
    market_rows = cache.get(key)
    if market_rows is None:
        totals = {
            r["shop"]: r["t"]
            for r in Sale.objects.filter(shop__market_id=shop.market_id,
                                         **since_day("created_at", since))
            .values("shop").annotate(t=Sum("total"))
        }
        market_rows = [(sid, cat, totals.get(sid, 0)) for sid, cat in Shop.objects.filter(
            market_id=shop.market_id, is_active=True).values_list("id", "category_id")]
        cache.set(key, market_rows, RATING_CACHE_SECONDS)

    def rank_within(rows):
        ordered = [sid for sid, _cat, _t in sorted(rows, key=lambda r: -r[2])]
        pos = ordered.index(shop.id) + 1 if shop.id in ordered else len(ordered)
        return pos, len(ordered)

    overall_pos, overall_total = rank_within(market_rows)
    cat_rows = [r for r in market_rows if r[1] == shop.category_id] if shop.category_id else market_rows
    cat_pos, cat_total = rank_within(cat_rows)

    my_sales = (
        Sale.objects.filter(shop=shop, **since_day("created_at", since)).aggregate(s=Sum("total"))["s"]
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

    from django.core.cache import cache
    from django.db.models import Sum

    my_prods = list(Product.objects.filter(
        shop=shop, is_active=True, category__isnull=False
    ).select_related("category"))
    cats = sorted({p.category_id for p in my_prods})
    if not cats:
        return []
    # Faqat sotuvchi mahsulotlari toifalari bo'yicha (butun bozorning hamma mahsuloti emas) va
    # (bozor, toifalar, kun) bo'yicha 10 daqiqa kesh — eng og'ir so'rov (SaleItem × Sale)
    key = f"rating:prod:{shop.market_id}:{since.isoformat()}:{','.join(map(str, cats))}"
    sold = cache.get(key)
    if sold is None:
        sold = {
            row["product"]: row["q"]
            for row in SaleItem.objects.filter(
                sale__shop__market_id=shop.market_id,
                **since_day("sale__created_at", since),
                product__category_id__in=cats,
            )
            .values("product")
            .annotate(q=Sum("quantity"))
        }
        cache.set(key, sold, RATING_CACHE_SECONDS)
    # Bozordagi shu toifalardagi mahsulotlar toifa bo'yicha guruhlanadi
    cat_products = defaultdict(list)  # category_id -> [(product_id, qty)]
    for mp in Product.objects.filter(
        shop__market_id=shop.market_id, category_id__in=cats, is_active=True
    ).values("id", "category_id"):
        cat_products[mp["category_id"]].append((mp["id"], sold.get(mp["id"], 0)))

    ranks = []
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
def register(request):
    """Kassa (POS): bugungi tushum to'lov turi bo'yicha + maydalik + kunni yopish (Z-hisobot)."""
    from .services.cash import (
        CashError,
        can_set_opening,
        close_register,
        register_totals,
        set_opening,
    )

    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    today = timezone.localdate()

    if request.method == "POST":
        try:
            if request.POST.get("action") == "opening":
                set_opening(shop, today, to_int(request.POST.get("opening_cash")), request.user)
                messages.success(request, "Ertalabki maydalik saqlandi.")
                from django.utils.http import url_has_allowed_host_and_scheme

                nxt = request.POST.get("next", "")
                ok = url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()})
                return redirect(nxt if ok and nxt else "seller:register")
            _z, diff = close_register(
                shop, today, to_int(request.POST.get("counted_cash")), request.user,
                note=request.POST.get("note", ""),
            )
        except CashError as e:
            messages.error(request, str(e))
            return redirect("seller:register")
        if diff == 0:
            messages.success(request, "Kassa yopildi. Naqd to'liq mos keldi.")
        elif diff < 0:
            messages.warning(request, f"Kassa yopildi. Kamomad: {som(-diff)} so'm.")
        else:
            messages.warning(request, f"Kassa yopildi. Ortiqcha: {som(diff)} so'm.")
        return redirect("seller:register")

    t = register_totals(shop, today)
    return render(
        request,
        "seller/register.html",
        {
            "shop": shop,
            "t": t,
            "today_close": RegisterClose.objects.filter(shop=shop, date=today).first(),
            "can_open": can_set_opening(shop, today),
            "recent": Sale.objects.filter(shop=shop, **on_day("created_at", today)).order_by(
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
            Sale, pk=_pk(request.POST.get("sale")), shop=shop, **on_day("created_at", today))
        new_total = to_int(request.POST.get("new_total"), 0) or 0
        reason = request.POST.get("reason", "").strip()[:200]
        if new_total <= 0 or not reason:
            messages.error(request, "Yangi summa (0 dan katta) va sabab kiritilishi shart.")
        elif new_total == sale.total:
            messages.error(request, "Yangi summa eskisidan farq qilmaydi.")
        elif sale.debt_records.filter(paid_amount__gt=0).exists():
            messages.error(request, "Bu nasiya chekiga to'lov qilingan — summani o'zgartirib bo'lmaydi.")
        else:
            # Nasiyaga sotilgan chek — daftardagi qarz ham shu summaga tenglashadi
            sale.debt_records.filter(is_paid=False).update(amount=new_total)
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
            "sales": Sale.objects.filter(shop=shop, **on_day("created_at", today)).order_by("-created_at"),
            "history": Correction.objects.filter(shop=shop).select_related("user")[:30],
        },
    )


def _pending_nosales(shop):
    """Tushuntirilmagan 'savdo yo'q' signallari (e'tiroz biriktirilmagan)."""
    from apps.analytics.models import Alert

    # Faqat TUGAGAN kunlar: bugun hali savdo qilish mumkin — tushuntirish talab qilinmaydi
    return (
        Alert.objects.filter(shop=shop, kind=Alert.Kind.ZERO_SALES, status=Alert.Status.NEW)
        .filter(date__lt=timezone.localdate(), appeals__isnull=True)
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
                pk=_pk(alert_id), shop=shop, kind=Alert.Kind.ZERO_SALES
            ).first()
            if alert and msg:
                # Signal OCHIQ qoladi — izoh nazoratchiga e'tiroz sifatida boradi.
                # Ilgari sotuvchi istalgan matn yozib qizil signalni o'zi yopib yuborardi.
                Appeal.objects.create(
                    shop=shop, alert=alert, author=request.user, message=msg[:2000]
                )
                messages.success(request, "Izoh yuborildi. Nazoratchi ko'rib chiqadi.")
        elif msg:
            # Qaysi signalga e'tiroz — nazoratchi aynan qaysi kunni ko'rib chiqishni bilsin
            target = None
            if request.POST.get("alert"):
                target = Alert.objects.filter(pk=_pk(request.POST.get("alert")), shop=shop).first()
            Appeal.objects.create(shop=shop, alert=target, author=request.user, message=msg[:2000])
            messages.success(request, "E'tiroz yuborildi. Inspektor ko'rib chiqadi.")
        return redirect("seller:appeals")
    since = timezone.localdate() - timedelta(days=14)
    return render(
        request,
        "seller/appeals.html",
        {
            "shop": shop,
            "appeals": shop.appeals.select_related("author", "alert")[:30],
            "nosales": _pending_nosales(shop),
            "my_alerts": Alert.objects.filter(
                shop=shop, date__gte=since, status__in=(Alert.Status.NEW, Alert.Status.ASSIGNED)
            ).exclude(kind=Alert.Kind.ZERO_SALES).order_by("-date")[:20],
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
