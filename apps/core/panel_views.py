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
    return render(
        request, "panel/users.html", {"users": users[:300], "role": role or "", "q": q or ""}
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
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"{user.username}: {'faol' if user.is_active else 'bloklandi'}")
    return redirect("panel:users")


@superadmin_required
def account_create(request):
    """Bittalab hisob ochish: sotuvchi (do'kon bilan) yoki tekshiruvchi."""
    if request.method == "POST":
        role = request.POST.get("role")
        if role == Role.SELLER:
            shop = get_object_or_404(Shop, pk=request.POST.get("shop"))
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
    return render(
        request,
        "panel/account_create.html",
        {
            "shops": Shop.objects.select_related("market").filter(staff__isnull=True),
            "markets": Market.objects.all(),
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
