"""Super admin paneli: hisob ochish, import, sozlamalar, audit."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User
from apps.accounts.services import create_inspector, create_seller, reset_password
from apps.catalog.models import ShopCategory
from apps.geo.models import Market, Region, Row
from apps.shops.models import Shop

from .models import AuditLog, SystemSettings


def superadmin_required(view):
    @wraps(view)
    @login_required
    def _wrapped(request, *a, **kw):
        if not request.user.is_superadmin:
            return render(request, "panel/403.html", status=403)
        return view(request, *a, **kw)

    return _wrapped


@superadmin_required
def dashboard(request):
    ctx = {
        "regions": Region.objects.count(),
        "markets": Market.objects.count(),
        "shops": Shop.objects.count(),
        "sellers": User.objects.filter(role=Role.SELLER).count(),
        "inspectors": User.objects.filter(role=Role.INSPECTOR).count(),
        "recent_audit": AuditLog.objects.select_related("user")[:10],
    }
    return render(request, "panel/dashboard.html", ctx)


@superadmin_required
def user_list(request):
    users = User.objects.select_related("shop").order_by("-date_joined")
    role = request.GET.get("role")
    if role:
        users = users.filter(role=role)
    q = request.GET.get("q")
    if q:
        users = users.filter(username__icontains=q)
    from apps.core.pagination import paginate

    page = paginate(request, users, per_page=50)
    return render(
        request,
        "panel/users.html",
        {
            "users": page.object_list,
            "page": page,
            "querystring": f"role={role or ''}&q={q or ''}",
            "role": role or "",
            "q": q or "",
        },
    )


@superadmin_required
@require_POST
def user_reset(request, pk):
    user = get_object_or_404(User, pk=pk)
    pw = reset_password(user)
    messages.success(
        request, f"{user.username} uchun yangi parol: {pw} (birinchi kirishda almashtiriladi)"
    )
    return redirect("panel:users")


@superadmin_required
@require_POST
def user_toggle(request, pk):
    user = get_object_or_404(User, pk=pk)
    # Himoya: o'zini yoki oxirgi faol superadminni bloklash mumkin emas
    # (aks holda tizimga hech kim kira olmay qoladi).
    if user.is_active:
        if user.pk == request.user.pk:
            messages.error(request, "O'zingizni bloklay olmaysiz.")
            return redirect("panel:users")
        if user.is_superadmin:
            from django.db.models import Q

            others = (
                User.objects.filter(is_active=True)
                .filter(Q(role=Role.SUPERADMIN) | Q(is_superuser=True))
                .exclude(pk=user.pk)
                .exists()
            )
            if not others:
                messages.error(request, "Oxirgi faol super adminни bloklab bo'lmaydi.")
                return redirect("panel:users")
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"{user.username}: {'faol' if user.is_active else 'bloklandi'}")
    return redirect("panel:users")


def _next_shop_number(market) -> str:
    """Bozordagi eng katta raqamli do'kon +1 (betakror). Raqamlar unikal bo'lsin."""
    nums = [
        int(n)
        for n in Shop.objects.filter(market=market).values_list("number", flat=True)
        if str(n).isdigit()
    ]
    return str((max(nums) + 1) if nums else 1)


@superadmin_required
def account_create(request):
    """Bittalab hisob ochish: sotuvchi (do'kon bilan) yoki tekshiruvchi."""
    if request.method == "POST":
        role = request.POST.get("role")
        if role == Role.SELLER:
            # "mode" formadan: mavjud do'kon faqat existing rejimda ishlatiladi
            # (yangi rejimda yashirin shop select qiymati e'tiborga olinmaydi).
            mode = request.POST.get("mode", "new")
            existing = request.POST.get("shop") if mode == "existing" else None
            if mode == "existing" and not existing:
                messages.error(request, "Mavjud do'konni tanlang.")
                return redirect("panel:account_create")
            if existing:
                shop = get_object_or_404(Shop, pk=existing)
            else:
                # Yangi do'kon: STIR, bozor, savdo turi, manzil, lokatsiya (xaritadan)
                market = get_object_or_404(Market, pk=request.POST.get("market"))
                category = ShopCategory.objects.filter(pk=request.POST.get("category") or 0).first()
                if category is None:
                    messages.error(request, "Savdo turini tanlang.")
                    return redirect("panel:account_create")

                # Do'kon raqami UNIKAL: bo'sh yoki band bo'lsa — keyingi bo'sh raqam
                number = request.POST.get("number", "").strip()[:20]
                if not number or Shop.objects.filter(market=market, number=number).exists():
                    number = _next_shop_number(market)

                shop = Shop.objects.create(
                    market=market,
                    number=number,
                    stir=request.POST.get("stir", "").strip()[:15],
                    owner_name=request.POST.get("full_name", "").strip()[:200],
                    owner_phone=request.POST.get("phone", "").strip()[:20],
                    address=request.POST.get("address", "").strip()[:300],
                    category=category,
                    latitude=_f(request.POST.get("latitude")),
                    longitude=_f(request.POST.get("longitude")),
                )
            cred = create_seller(
                shop,
                full_name=request.POST.get("full_name", ""),
                phone=request.POST.get("phone", ""),
            )
        else:
            markets = Market.objects.filter(pk__in=request.POST.getlist("markets"))
            cred = create_inspector(
                request.POST.get("full_name", "Inspektor"),
                list(markets),
                phone=request.POST.get("phone", ""),
            )
        request.session["login_sheet"] = [cred_serializable(cred)]
        messages.success(request, "Hisob ochildi. Login varaqasi tayyor.")
        return redirect("panel:login_sheet")
    markets = list(Market.objects.all())
    next_by_market = {m.pk: _next_shop_number(m) for m in markets}
    return render(
        request,
        "panel/account_create.html",
        {
            "shops": Shop.objects.select_related("market").filter(staff__isnull=True),
            "markets": markets,
            "next_by_market": next_by_market,
            "categories": ShopCategory.objects.all(),
            "roles": [(Role.SELLER, "Sotuvchi"), (Role.INSPECTOR, "Tekshiruvchi")],
        },
    )


def cred_serializable(cred):
    return {
        "name": cred["name"],
        "login": cred["login"],
        "password": cred["password"],
        "shop": cred["shop"],
    }


@superadmin_required
def import_shops(request):
    """Excel'dan ommaviy do'kon + sotuvchi. Ustunlar: Raqam, STIR, Egasi, Telefon, Toifa, Qator."""
    if request.method == "POST" and request.FILES.get("file"):
        import openpyxl

        market = get_object_or_404(Market, pk=request.POST.get("market"))
        wb = openpyxl.load_workbook(request.FILES["file"], data_only=True)
        ws = wb.active
        created = []
        errors = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            try:
                number = str(row[0]).strip()
                stir = str(row[1]).strip() if row[1] else ""
                owner = str(row[2]).strip() if row[2] else ""
                phone = str(row[3]).strip() if row[3] else ""
                cat_name = str(row[4]).strip() if len(row) > 4 and row[4] else ""
                row_name = str(row[5]).strip() if len(row) > 5 and row[5] else ""
                category = ShopCategory.objects.filter(name=cat_name).first() if cat_name else None
                row_obj = (
                    Row.objects.get_or_create(market=market, label=row_name)[0]
                    if row_name
                    else None
                )
                shop, _ = Shop.objects.get_or_create(
                    market=market,
                    number=number,
                    defaults={
                        "stir": stir,
                        "owner_name": owner,
                        "owner_phone": phone,
                        "category": category,
                        "row": row_obj,
                    },
                )
                if not shop.staff.exists():
                    created.append(
                        cred_serializable(create_seller(shop, full_name=owner, phone=phone))
                    )
            except Exception:
                errors += 1
        request.session["login_sheet"] = created
        messages.success(request, f"{len(created)} ta hisob ochildi, {errors} ta xato.")
        return redirect("panel:login_sheet")
    return render(request, "panel/import_shops.html", {"markets": Market.objects.all()})


@superadmin_required
def login_sheet(request):
    creds = request.session.get("login_sheet", [])
    return render(request, "panel/login_sheet.html", {"creds": creds})


@superadmin_required
def import_cash(request):
    """Kassa/deklaratsiya Excel. Ustunlar: STIR, Sana(YYYY-MM-DD), Summa."""
    if request.method == "POST" and request.FILES.get("file"):
        import datetime

        import openpyxl

        from apps.cash.models import CashRecord

        wb = openpyxl.load_workbook(request.FILES["file"], data_only=True)
        ws = wb.active
        added, skipped = 0, 0
        dates = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            shop = Shop.objects.filter(stir=str(row[0]).strip()).first()
            if not shop:
                skipped += 1
                continue
            try:
                d = row[1]
                if isinstance(d, datetime.datetime):
                    d = d.date()
                elif isinstance(d, str):
                    d = datetime.datetime.strptime(d, "%Y-%m-%d").date()
                CashRecord.objects.update_or_create(
                    shop=shop, date=d, source="excel", defaults={"amount": int(row[2] or 0)}
                )
                dates.add(d)
                added += 1
            except (ValueError, TypeError):
                skipped += 1
        # Ta'sirlangan kunlar bo'yicha rostlikni qayta hisoblaymiz
        from apps.analytics.scoring.services import recompute_for_date

        for d in dates:
            recompute_for_date(d)
        messages.success(
            request, f"{added} ta yozuv yuklandi, {skipped} o'tkazib yuborildi. Rostlik yangilandi."
        )
        return redirect("panel:import_cash")
    return render(request, "panel/import_cash.html")


@superadmin_required
def settings_edit(request):
    s = SystemSettings.get_solo()
    if request.method == "POST":
        fields = [
            "green_threshold",
            "yellow_threshold",
            "weight_cash",
            "weight_camera",
            "weight_stock",
            "weight_price",
            "weakest_part_cap",
            "max_discount_no_cost_pct",
            "rounding_max",
            "login_max_attempts",
            "login_lock_minutes",
            "tax_rate_percent",
            "fine_penalty_percent",
            "anomaly_drop_pct",
            "cash_shortage_pct",
        ]
        for f in fields:
            val = request.POST.get(f)
            if val is not None and val != "":
                setattr(s, f, int(val))
        s.save()
        SystemSettings._cache = None
        messages.success(request, "Sozlamalar saqlandi.")
        return redirect("panel:settings")
    return render(request, "panel/settings.html", {"s": s})


@superadmin_required
def audit_log(request):
    logs = AuditLog.objects.select_related("user").all()
    action = request.GET.get("action")
    if action:
        logs = logs.filter(action=action)
    return render(
        request,
        "panel/audit.html",
        {"logs": logs[:400], "action": action or "", "actions": AuditLog.Action.choices},
    )


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@superadmin_required
def markets(request):
    """Bozorlar va viloyatlar boshqaruvi — qo'shish/tahrirlash (django-adminsiz)."""
    if request.method == "POST":
        act = request.POST.get("action")
        if act == "add_region":
            name = request.POST.get("region_name", "").strip()[:120]
            if name:
                Region.objects.get_or_create(name=name)
                messages.success(request, "Viloyat qo'shildi.")
        elif act == "save_market":
            region = Region.objects.filter(pk=request.POST.get("region") or 0).first()
            name = request.POST.get("name", "").strip()[:150]
            if not (region and name):
                messages.error(request, "Viloyat va nom kerak.")
                return redirect("panel:markets")
            data = {
                "region": region,
                "name": name,
                "address": request.POST.get("address", "").strip()[:300],
                "latitude": _f(request.POST.get("latitude")),
                "longitude": _f(request.POST.get("longitude")),
            }
            mid = request.POST.get("market_id")
            if mid:
                Market.objects.filter(pk=mid).update(**data)
                messages.success(request, "Bozor yangilandi.")
            else:
                Market.objects.create(**data)
                messages.success(request, "Bozor qo'shildi.")
        return redirect("panel:markets")
    from django.db.models import Count

    return render(
        request,
        "panel/markets.html",
        {
            "regions": Region.objects.all(),
            "markets": Market.objects.select_related("region").annotate(
                nshops=Count("shops")
            ),
        },
    )


@superadmin_required
def market_detail(request, pk):
    """Bozordagi do'konlar + har do'kon sotuvchisi login/paroli."""
    market = get_object_or_404(Market.objects.select_related("region"), pk=pk)
    shops = list(
        market.shops.select_related("category", "row").prefetch_related("staff")
    )
    # Raqamli tartib: "2" "10" dan oldin (satr tartibi emas)
    shops.sort(key=lambda s: (0, int(s.number)) if s.number.isdigit() else (1, s.number))
    rows = []
    for s in shops:
        seller = s.staff.first()  # do'kon sotuvchisi (odatda bitta)
        rows.append({"shop": s, "seller": seller})
    return render(request, "panel/market_detail.html", {"market": market, "rows": rows})


@superadmin_required
def categories(request):
    """Savdo turlari (ShopCategory) — qo'shish/o'chirish."""
    if request.method == "POST":
        act = request.POST.get("action")
        if act == "add":
            name = request.POST.get("name", "").strip()[:120]
            if name:
                ShopCategory.objects.get_or_create(name=name)
                messages.success(request, "Savdo turi qo'shildi.")
        elif act == "delete":
            cat = ShopCategory.objects.filter(pk=request.POST.get("id") or 0).first()
            if cat is None:
                messages.error(request, "Savdo turi topilmadi.")
            elif cat.shops.exists() or cat.product_categories.exists():
                # Ishlatilayotgan turni o'chirsa, do'konlar turi jimgina yo'qoladi.
                messages.error(
                    request,
                    f"“{cat.name}” ishlatilmoqda "
                    f"({cat.shops.count()} do'kon) — avval bo'shatib oling.",
                )
            else:
                cat.delete()
                messages.success(request, "O'chirildi.")
        return redirect("panel:categories")
    from django.db.models import Count

    return render(
        request,
        "panel/categories.html",
        {"categories": ShopCategory.objects.annotate(
            nshops=Count("shops", distinct=True),
            nprod=Count("product_categories", distinct=True))},
    )


@superadmin_required
def cameras(request):
    """Kameralar boshqaruvi — qo'shish, token ko'rish (django-adminsiz)."""
    from apps.cameras.models import Camera

    if request.method == "POST":
        act = request.POST.get("action")
        if act == "add":
            market = Market.objects.filter(pk=request.POST.get("market") or 0).first()
            if not market:
                messages.error(request, "Bozorni tanlang.")
                return redirect("panel:cameras")
            shop = Shop.objects.filter(pk=request.POST.get("shop") or 0).first()
            Camera.objects.create(
                name=request.POST.get("name", "").strip()[:120] or "Kamera",
                market=market,
                shop=shop,
                kind=request.POST.get("kind", "counter"),
                rtsp_sub=request.POST.get("rtsp_sub", "").strip()[:500],
            )
            messages.success(request, "Kamera qo'shildi. Token ro'yxatda ko'rinadi.")
        elif act == "toggle":
            cam = Camera.objects.filter(pk=request.POST.get("id") or 0).first()
            if cam:
                cam.is_active = not cam.is_active
                cam.save(update_fields=["is_active"])
        elif act == "delete":
            Camera.objects.filter(pk=request.POST.get("id") or 0).delete()
            messages.success(request, "Kamera o'chirildi.")
        return redirect("panel:cameras")
    from apps.cameras.models import Camera as Cam

    return render(
        request,
        "panel/cameras.html",
        {
            "cameras": Cam.objects.select_related("market", "shop"),
            "markets": Market.objects.all(),
            "shops": Shop.objects.select_related("market").order_by("market__name", "number"),
            "kinds": Cam.Kind.choices,
        },
    )
