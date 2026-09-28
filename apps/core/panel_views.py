"""Super admin paneli: hisob ochish, import, sozlamalar, audit."""

import logging
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User
from apps.accounts.services import create_inspector, create_seller, reset_password
from apps.catalog.models import ShopCategory
from apps.geo.models import Market, Region, Row
from apps.shops.models import Shop

from .format import PHONE_ERROR, clean_phone, to_int
from .models import AuditLog, SystemSettings


def _pk(value) -> int:
    """So'rovdan kelgan ID — raqam bo'lmasa 0 (500 xato o'rniga "topilmadi")."""
    return to_int(value, 0) or 0


def _digits(value) -> str:
    """STIR faqat raqam: "300 000 001" → "300000001" (login ham shundan)."""
    return "".join(c for c in str(value or "") if c.isdigit())


def _load_xlsx(request):
    """Excel faylni ochadi; .xlsx bo'lmasa yoki buzuq bo'lsa — None (500 emas)."""
    import openpyxl

    f = request.FILES.get("file")
    if f is None:
        return None
    if f.size and f.size > 10 * 1024 * 1024:
        messages.error(request, "Fayl juda katta (10 MB dan ortiq) — bo'lib yuklang.")
        return None
    try:
        return openpyxl.load_workbook(f, data_only=True, read_only=True)
    except Exception:  # noqa: BLE001 — BadZipFile, InvalidFileException va h.k.
        messages.error(request, "Fayl ochilmadi — .xlsx formatidagi Excel fayl yuklang.")
        return None


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
        **_backup_status(),
        **_sms_status(),
        "health": _health(),
    }
    return render(request, "panel/dashboard.html", ctx)


def _health() -> dict:
    from .health import run

    return run(full=True)


def _sms_status() -> dict:
    """SMS (xaridorga nasiya eslatmasi): ulanganmi, oxirgi 7 kun yuborilgan/xato."""
    from datetime import timedelta

    from django.conf import settings
    from django.db.models import Count, Q
    from django.utils import timezone

    from .models import SmsMessage

    week = SmsMessage.objects.filter(created_at__gte=timezone.now() - timedelta(days=7))
    agg = week.aggregate(sent=Count("id", filter=Q(status="sent")),
                         failed=Count("id", filter=Q(status="failed")),
                         invalid=Count("id", filter=Q(status="invalid")))
    return {"sms_backend": settings.SMS_BACKEND, "sms_week": agg,
            "sms_last_error": week.filter(status="failed").first()}


def _backup_status() -> dict:
    """Zaxira holati: oxirgi muvaffaqiyatli nusxa qachon, tashqariga ketdimi, eskirganmi."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import BackupLog

    last = BackupLog.objects.first()
    last_ok = BackupLog.objects.filter(ok=True).first()
    stale = last_ok is None or timezone.now() - last_ok.created_at > timedelta(hours=26)
    return {"backup_last": last, "backup_last_ok": last_ok, "backup_stale": stale}


@superadmin_required
@require_POST
def backup_now(request):
    """Hozir zaxira olish (admin tugmasi). Katta bazada uzoq davom etishi mumkin."""
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("backup", stdout=out)
    from .models import BackupLog

    log = BackupLog.objects.first()
    request.audit_detail = f"Zaxira nusxa qo'lda: {'OK' if log and log.ok else 'XATO'}"
    if log and log.ok:
        messages.success(request, f"Zaxira olindi: {len(log.files)} fayl, "
                                  f"{log.total_bytes / 1e6:.1f} MB.")
        if not log.offsite_ok:
            messages.warning(request, "Zaxira faqat shu serverda — tashqi joyga yuborish "
                                      "(BACKUP_UPLOAD_CMD) sozlanmagan.")
    else:
        messages.error(request, "Zaxira olinmadi: " + (log.message[:200] if log else "noma'lum"))
    return redirect("panel:home")


@superadmin_required
def user_list(request):
    users = User.objects.select_related("shop").order_by("-date_joined")
    role = request.GET.get("role")
    if role:
        users = users.filter(role=role)
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        users = users.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(shop__number=q)
            | Q(shop__stir__icontains=q)
        )
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
    request.audit_detail = f"Parol tiklandi: {user.username}"
    messages.success(
        request, f"{user.username} uchun yangi parol: {pw} (birinchi kirishda almashtiriladi)"
    )
    return redirect("panel:users")


@superadmin_required
@require_POST
def user_password_reveal(request, pk):
    """Parolni ko'rsatish — faqat tugma bosilganda va AUDIT bilan.

    Oldin parollar har sahifa yuklanishida HTML'ga yozilardi ("ko'rsatish" faqat yashirardi —
    sahifa manbasida hammasi ochiq) va nusxa tugmasi inline JS satriga qo'yilardi: sotuvchi
    o'ziga ') bilan boshlanadigan parol qo'ysa, admin brauzerida uning kodi ishlardi (saqlangan XSS).
    Endi qiymat JSON bilan keladi va matn sifatida chiqadi; kim kimning parolini ko'rgani jurnalda.
    """
    from django.http import JsonResponse

    user = get_object_or_404(User, pk=pk)
    if not user.visible_password:
        return JsonResponse({"detail": "Parol saqlanmagan — kerak bo'lsa tiklang."}, status=404)
    request.audit_detail = f"Parol ko'rildi: {user.username}"
    return JsonResponse({"password": user.visible_password})


@superadmin_required
@require_POST
def user_2fa_reset(request, pk):
    """Telefon yo'qolgan xodim: 2FA bekor qilinadi, keyingi kirishda qayta ulaydi."""
    user = get_object_or_404(User, pk=pk)
    user.totp_secret, user.totp_enabled, user.totp_last_step, user.backup_codes = "", False, 0, []
    user.save(update_fields=["totp_secret", "totp_enabled", "totp_last_step", "backup_codes"])
    request.audit_detail = f"2FA bekor qilindi: {user.username}"
    messages.success(request, f"{user.get_full_name() or user.username}: ikki bosqichli himoya "
                              "bekor qilindi — keyingi kirishda qayta ulaydi.")
    return redirect("panel:user_edit", pk=user.pk)


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
                messages.error(request, "Oxirgi faol super adminni bloklab bo'lmaydi.")
                return redirect("panel:users")
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    request.audit_detail = f"{user.username}: {'faollashtirildi' if user.is_active else 'bloklandi'}"
    messages.success(request, f"{user.username}: {'faol' if user.is_active else 'bloklandi'}")
    return redirect("panel:users")


def _taken_numbers() -> dict:
    """{bozor_id: {raqam: egasi}} — formada yozayotgandayoq "band" deb ko'rsatish uchun."""
    out = {}
    for mid, num, owner in Shop.objects.values_list("market_id", "number", "owner_name"):
        out.setdefault(str(mid), {})[str(num)] = owner or "—"
    return out


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
        if not request.POST.get("full_name", "").strip():
            messages.error(request, "F.I.O. ni yozing.")
            return redirect("panel:account_create")
        phone = clean_phone(request.POST.get("phone"))
        if phone is None:
            messages.error(request, PHONE_ERROR)
            return redirect("panel:account_create")
        if role == Role.SELLER:
            # "mode" formadan: mavjud do'kon faqat existing rejimda ishlatiladi
            # (yangi rejimda yashirin shop select qiymati e'tiborga olinmaydi).
            mode = request.POST.get("mode", "new")
            existing = request.POST.get("shop") if mode == "existing" else None
            if mode == "existing" and not existing:
                messages.error(request, "Mavjud do'konni tanlang.")
                return redirect("panel:account_create")
            if existing:
                shop = get_object_or_404(Shop, pk=_pk(existing))
            else:
                # Yangi do'kon: STIR, bozor, savdo turi, manzil, lokatsiya (xaritadan)
                market = get_object_or_404(Market, pk=_pk(request.POST.get("market")))
                category = ShopCategory.objects.filter(pk=_pk(request.POST.get("category"))).first()
                if category is None:
                    messages.error(request, "Savdo turini tanlang.")
                    return redirect("panel:account_create")
                if not category.product_categories.exists():
                    messages.error(request, f"«{category.name}» savdo turida mahsulot turi yo'q — sotuvchi bo'sh "
                                            "ro'yxat ko'rardi. Avval Savdo turlari sahifasida qo'shing.")
                    return redirect("panel:account_create")
                if not _digits(request.POST.get("stir")):
                    messages.error(request, "STIR ni yozing (login shundan hosil bo'ladi).")
                    return redirect("panel:account_create")

                # Do'kon raqami UNIKAL. Bo'sh — keyingi bo'sh raqam. Band bo'lsa — XATO (ilgari jimgina
                # keyingisi berilardi: 27 yozilsa 28 bo'lib qolardi, admin sezmasdi)
                number = request.POST.get("number", "").strip()[:20]
                if not number:
                    number = _next_shop_number(market)
                else:
                    taken = Shop.objects.filter(market=market, number=number).first()
                    if taken is not None:
                        messages.error(request, f"№{number} «{market.name}» bozorida band (egasi: "
                                                f"{taken.owner_name or '—'}). Boshqa raqam yozing yoki bo'sh "
                                                f"qoldiring — keyingi bo'sh raqam №{_next_shop_number(market)} beriladi.")
                        return redirect("panel:account_create")

                shop = Shop.objects.create(
                    market=market,
                    number=number,
                    stir=_digits(request.POST.get("stir"))[:15],
                    owner_name=request.POST.get("full_name", "").strip()[:200],
                    owner_phone=phone,
                    address=request.POST.get("address", "").strip()[:300],
                    category=category,
                    # Koordinata so'ralmaydi — bozor markazi olinadi (xarita uchun kifoya)
                    latitude=market.latitude,
                    longitude=market.longitude,
                )
            cred = create_seller(
                shop,
                full_name=request.POST.get("full_name", ""),
                phone=phone,
            )
        elif role == Role.PROSECUTOR:
            # Kuzatuvchi: bozor tanlanmasa — butun respublika (faqat ko'rish)
            from apps.accounts.services import create_prosecutor

            markets = Market.objects.filter(
                pk__in=[_pk(x) for x in request.POST.getlist("markets")]
            )
            cred = create_prosecutor(request.POST.get("full_name", ""), list(markets), phone=phone)
        else:
            markets = Market.objects.filter(
                pk__in=[_pk(x) for x in request.POST.getlist("markets")]
            )
            if not markets.exists():
                # Bozorsiz inspektor hech narsa ko'rmaydi — foydasiz hisob ochilmasin
                messages.error(request, "Inspektorga kamida bitta bozor biriktiring.")
                return redirect("panel:account_create")
            cred = create_inspector(
                request.POST.get("full_name", "Inspektor"),
                list(markets),
                phone=phone,
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
            "taken_numbers": _taken_numbers(),
            "categories": ShopCategory.objects.all(),
            "roles": [(Role.SELLER, "Sotuvchi"), (Role.INSPECTOR, "Tekshiruvchi"),
                      (Role.PROSECUTOR, "Prokuror (kuzatuvchi)")],
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
        market = get_object_or_404(Market, pk=_pk(request.POST.get("market")))
        # Ustunda savdo turi bo'lmasa — formada tanlangan standart tur olinadi
        default_cat = ShopCategory.objects.filter(pk=_pk(request.POST.get("category"))).first()
        wb = _load_xlsx(request)
        if wb is None:
            return redirect("panel:import_shops")
        ws = wb.active
        from apps.core.format import excel_str

        created = []
        errors = 0
        bad_rows = []
        phone_warn = []
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or row[0] is None:
                continue
            try:
                # Excel sonni float saqlaydi: 25.0 -> "25" (aks holda raqam "25.0" bo'lardi)
                number = excel_str(row[0])
                stir = _digits(excel_str(row[1]))[:15] if len(row) > 1 else ""
                owner = excel_str(row[2]) if len(row) > 2 else ""
                raw_phone = excel_str(row[3]) if len(row) > 3 else ""
                phone = clean_phone(raw_phone)
                if phone is None:  # do'kon baribir ochiladi, telefon keyin tuzatiladi
                    phone_warn.append(f"{idx}-qator ({raw_phone})")
                    phone = ""
                cat_name = excel_str(row[4]) if len(row) > 4 else ""
                row_name = excel_str(row[5]) if len(row) > 5 else ""
                if not number:
                    raise ValueError("raqam bo'sh")
                if not stir:
                    raise ValueError("STIR bo'sh")
                if cat_name:
                    category = ShopCategory.objects.filter(name__iexact=cat_name).first()
                    if category is None:
                        raise ValueError(f"savdo turi «{cat_name}» topilmadi")
                else:
                    category = default_cat
                if category is None:
                    # Turisiz do'kon o'xshashlar bilan solishtirilmaydi — jimgina o'tkazmaymiz
                    raise ValueError("savdo turi yo'q (ustunga yozing yoki standartini tanlang)")
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
            except Exception as e:  # noqa: BLE001 — qator xatosi importni to'xtatmasin
                errors += 1
                bad_rows.append(f"{idx}-qator ({e})")
        request.session["login_sheet"] = created
        messages.success(request, f"{len(created)} ta hisob ochildi, {errors} ta xato.")
        if bad_rows:
            messages.warning(request, "Xato qatorlar: " + "; ".join(bad_rows[:10])
                             + (" ..." if len(bad_rows) > 10 else ""))
        if phone_warn:
            messages.warning(request, "Telefon noto'g'ri — bo'sh qoldirildi (do'kon sahifasida tuzating): "
                             + "; ".join(phone_warn[:10]) + (" ..." if len(phone_warn) > 10 else ""))
        return redirect("panel:login_sheet")
    return render(
        request,
        "panel/import_shops.html",
        {"markets": Market.objects.all(), "categories": ShopCategory.objects.order_by("name")},
    )


@superadmin_required
def login_sheet(request):
    # Parollar FAQAT BIR MARTA ko'rsatiladi — sessiyadan olib tashlaymiz
    # (ilgari sahifani qayta ochganda ochiq parollar yana ko'rinardi).
    creds = request.session.pop("login_sheet", [])
    return render(request, "panel/login_sheet.html", {"creds": creds})


@superadmin_required
def import_cash(request):
    """Kassa/deklaratsiya Excel. Ustunlar: STIR, Sana(YYYY-MM-DD), Summa."""
    if request.method == "POST" and request.FILES.get("file"):
        from django.utils import timezone

        from apps.cash.adapters.base import AdapterError, parse_amount, parse_date
        from apps.cash.models import CashRecord
        from apps.core.format import excel_str

        wb = _load_xlsx(request)
        if wb is None:
            return redirect("panel:import_cash")
        ws = wb.active
        today = timezone.localdate()
        added, skipped = 0, 0
        dates = set()
        reasons = []
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not row[0]:
                continue
            stir = _digits(excel_str(row[0]))
            number = excel_str(row[3]) if len(row) > 3 else ""
            qs = Shop.objects.filter(stir=stir)
            if number:
                qs = qs.filter(number=number)
            matches = list(qs[:2])
            if not matches:
                skipped += 1
                reasons.append(f"{idx}: STIR {stir} topilmadi")
                continue
            if len(matches) > 1:
                # Bitta egasi (STIR) bir nechta do'konga ega — qaysi biri ekani noma'lum
                skipped += 1
                reasons.append(f"{idx}: STIR {stir} bir nechta do'konda — 4-ustunga do'kon raqami yozing")
                continue
            shop = matches[0]
            try:
                # Soliq API bilan BITTA o'quvchi: "1,250,000.00", "1.250.000", "1 250 000 so'm",
                # Excel sana seriyasi (46289) — hammasi tushunarli (oldin ko'pi "noto'g'ri" deb tashlanardi)
                if row[1] in (None, ""):
                    raise ValueError("sana yo'q")
                d = parse_date(row[1])
                if d > today:
                    raise ValueError(f"sana kelajakda ({d:%d.%m.%Y})")
                amount = parse_amount(row[2] if len(row) > 2 else None)
                if amount < 0:
                    raise ValueError("summa manfiy")
                CashRecord.objects.update_or_create(
                    shop=shop, date=d, source="excel", defaults={"amount": amount}
                )
                dates.add(d)
                added += 1
            except (ValueError, TypeError, AdapterError) as e:
                skipped += 1
                reasons.append(f"{idx}: {e}")
        # Ta'sirlangan kunlar bo'yicha rostlikni qayta hisoblaymiz
        from apps.analytics.scoring.services import recompute_for_date

        for d in dates:
            recompute_for_date(d)
        messages.success(
            request, f"{added} ta yozuv yuklandi, {skipped} o'tkazib yuborildi. Rostlik yangilandi."
        )
        if reasons:
            messages.warning(request, "O'tkazilgan qatorlar: " + "; ".join(reasons[:10])
                             + (" ..." if len(reasons) > 10 else ""))
        return redirect("panel:import_cash")
    from apps.cash.models import DeclarationSync
    from apps.cash.sync import status as tax_status

    return render(request, "panel/import_cash.html", {
        "tax": tax_status(),
        "syncs": DeclarationSync.objects.all()[:8],
    })


@superadmin_required
@require_POST
def tax_sync_now(request):
    """Soliq / onlayn kassa deklaratsiyasini hozir olish (admin tugmasi)."""
    from apps.cash.sync import run_sync

    entry = run_sync()
    if entry is None:
        messages.warning(request, "Soliq integratsiyasi sozlanmagan (TAX_ADAPTER) — "
                                  "hozircha faqat Excel import.")
    elif entry.ok:
        request.audit_detail = f"Soliq sinxronlash: {entry.saved} do'kon-kun"
        messages.success(request, entry.message)
        if entry.unmatched:
            messages.warning(request, f"{entry.unmatched} ta qator do'konga bog'lanmadi: "
                             + "; ".join(entry.problems[:5]))
    else:
        request.audit_detail = "Soliq sinxronlash: XATO"
        messages.error(request, entry.message[:300])
    return redirect("panel:import_cash")


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
            "fine_small",
            "fine_medium",
            "fine_high",
            "anomaly_drop_pct",
            "cash_shortage_pct",
            "stockin_photo_min",
            "writeoff_alert_min",
            "correction_alert_pct",
            "correction_alert_min",
        ]
        # Har maydon uchun ruxsat etilgan oraliq (noto'g'ri qiymat tizimni buzmasin)
        limits = {
            "green_threshold": (1, 100), "yellow_threshold": (0, 99),
            "weight_cash": (0, 100), "weight_camera": (0, 100),
            "weight_stock": (0, 100), "weight_price": (0, 100),
            "weakest_part_cap": (0, 100), "max_discount_no_cost_pct": (0, 90),
            "rounding_max": (0, 100000),
            # 0/1 bo'lsa hamma (admin ham) birinchi xatodayoq bloklanardi
            "login_max_attempts": (3, 20), "login_lock_minutes": (1, 1440),
            "tax_rate_percent": (0, 100),
            "fine_small": (0, 10_000_000_000), "fine_medium": (0, 10_000_000_000),
            "fine_high": (0, 10_000_000_000),
            "anomaly_drop_pct": (1, 100), "cash_shortage_pct": (1, 100),
            "stockin_photo_min": (0, 1_000_000_000),
            "writeoff_alert_min": (0, 1_000_000_000),
            "correction_alert_pct": (1, 100), "correction_alert_min": (0, 1_000_000_000),
        }
        labels = {
            "green_threshold": "Yashil chegara", "yellow_threshold": "Sariq chegara",
            "weight_cash": "Kassa og'irligi", "weight_camera": "Kamera og'irligi",
            "weight_stock": "Qoldiq og'irligi", "weight_price": "Narx og'irligi",
            "weakest_part_cap": "Eng zaif qism ustamasi",
            "max_discount_no_cost_pct": "Maks. chegirma (%)", "rounding_max": "Yaxlitlash maks.",
            "login_max_attempts": "Kirish urinishlari", "login_lock_minutes": "Blok muddati",
            "tax_rate_percent": "Soliq stavkasi", "fine_small": "Kichik jarima",
            "fine_medium": "O'rta jarima", "fine_high": "Yuqori jarima",
            "anomaly_drop_pct": "Anomaliya chegarasi", "cash_shortage_pct": "Kassa kamomadi chegarasi",
            "stockin_photo_min": "Nakladnoy majburiy summa",
            "writeoff_alert_min": "Hisobdan chiqarish signali",
            "correction_alert_pct": "Tuzatish signali (%)", "correction_alert_min": "Tuzatish signali (so'm)",
        }
        new, errors = {}, []
        for f in fields:
            raw = request.POST.get(f)
            if raw is None or str(raw).strip() == "":
                continue
            val = to_int(raw)
            lo, hi = limits[f]
            if val is None or not (lo <= val <= hi):
                errors.append(f"{labels.get(f, f)}: {lo}–{hi} oralig'ida butun son bo'lsin")
            else:
                new[f] = val
        g = new.get("green_threshold", s.green_threshold)
        y = new.get("yellow_threshold", s.yellow_threshold)
        if not errors and g <= y:
            errors.append("Yashil chegara sariqdan katta bo'lsin")
        fs, fm, fh = (new.get(k, getattr(s, k)) for k in ("fine_small", "fine_medium", "fine_high"))
        if not errors and not (fs <= fm <= fh):
            errors.append("Jarimalar: kichik ≤ o'rta ≤ yuqori bo'lsin")
        weights = [new.get(k, getattr(s, k)) for k in
                   ("weight_cash", "weight_camera", "weight_stock", "weight_price")]
        if not errors and sum(weights) <= 0:
            errors.append("Og'irliklar yig'indisi 0 dan katta bo'lsin")
        # Kamera: xaridorga aylanish ulushi (0.01–1.00) — panelda (django-adminsiz)
        from decimal import Decimal

        from .format import to_dec

        raw_br = request.POST.get("buyer_ratio")
        if raw_br not in (None, ""):
            br = to_dec(raw_br)
            if br is None or not (Decimal("0.01") <= br <= Decimal("1")):
                errors.append("Xaridorga aylanish ulushi: 0.01–1.00 oralig'ida bo'lsin")
            else:
                new["buyer_ratio"] = br.quantize(Decimal("0.01"))
        # Chegirma tugmalari: "5, 10, 15" — 1..5 ta, har biri 1..50 %
        raw_dp = request.POST.get("discount_percents")
        if raw_dp not in (None, ""):
            parts = [x for x in raw_dp.replace(";", ",").split(",") if x.strip()]
            vals = [to_int(x) for x in parts]
            if not vals or len(vals) > 5 or any(v is None or not 1 <= v <= 50 for v in vals):
                errors.append("Chegirma foizlari: 1–5 ta son, har biri 1–50 (masalan: 5, 10, 15)")
            else:
                new["discount_percents"] = sorted(set(vals))
        if errors:
            for e in errors:
                messages.error(request, e)
            return redirect("panel:settings")
        if request.POST.get("require_2fa_staff_present"):
            new["require_2fa_staff"] = request.POST.get("require_2fa_staff") == "on"
        if request.POST.get("require_daily_close_present"):
            new["require_daily_close"] = request.POST.get("require_daily_close") == "on"
        changed = [f"{f}: {getattr(s, f)}→{v}" for f, v in new.items() if getattr(s, f) != v]
        for f, v in new.items():
            setattr(s, f, v)
        s.save()
        request.audit_detail = ("Sozlama: " + "; ".join(changed))[:300] if changed else ""
        request.audit_action = AuditLog.Action.SETTINGS
        # Bugungi ballar yangi og'irlik/chegaralar bilan darhol qayta hisoblansin
        try:
            from django.utils import timezone

            from apps.analytics.scoring.services import recompute_for_date

            recompute_for_date(timezone.localdate())
            messages.success(request, "Sozlamalar saqlandi. Bugungi ballar qayta hisoblandi.")
        except Exception:  # noqa: BLE001 — sozlama baribir saqlandi
            logging.getLogger(__name__).exception("Sozlamadan keyin qayta hisoblash yiqildi")
            messages.warning(request, "Sozlamalar saqlandi, lekin ballarni qayta hisoblab bo'lmadi — "
                                      "keyingi fon hisobida yangilanadi.")
        return redirect("panel:settings")
    return render(
        request,
        "panel/settings.html",
        {"s": s, "discount_percents": ", ".join(str(x) for x in (s.discount_percents or [])),
         "ip_max": django_settings.LOGIN_IP_MAX_FAILS,
         "ip_block": django_settings.LOGIN_IP_BLOCK_MINUTES},
    )


@superadmin_required
def audit_log(request):
    from django.db.models import Q

    from .pagination import paginate

    logs = AuditLog.objects.select_related("user").all()
    action = request.GET.get("action") or ""
    if action not in AuditLog.Action.values:
        action = ""
    if action:
        logs = logs.filter(action=action)
    q = (request.GET.get("q") or "").strip()
    if q:
        # Foydalanuvchi logini, yo'l yoki tafsilot bo'yicha (masalan do'kon raqami)
        logs = logs.filter(
            Q(user__username__icontains=q) | Q(path__icontains=q) | Q(detail__icontains=q)
        )
    page = paginate(request, logs, per_page=100)
    return render(
        request,
        "panel/audit.html",
        {
            "logs": page.object_list,
            "page": page,
            "querystring": f"action={action}&q={q}",
            "action": action,
            "q": q,
            "actions": AuditLog.Action.choices,
        },
    )


def _f(v, limit=None):
    """Koordinata: son bo'lmasa, nan/inf yoki chegaradan tashqari bo'lsa — None."""
    import math

    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or (limit is not None and abs(x) > limit):
        return None
    return x


@superadmin_required
def markets(request):
    """Bozorlar va viloyatlar boshqaruvi — qo'shish/tahrirlash (django-adminsiz)."""
    if request.method == "POST":
        act = request.POST.get("action")
        if act == "add_region":
            name = " ".join(request.POST.get("region_name", "").split())[:120]
            if not name:
                messages.error(request, "Viloyat nomini yozing.")
            elif Region.objects.filter(name__iexact=name).exists():
                messages.error(request, f"«{name}» viloyati allaqachon bor.")
            else:
                Region.objects.create(name=name)
                messages.success(request, "Viloyat qo'shildi.")
        elif act == "save_market":
            region = Region.objects.filter(pk=_pk(request.POST.get("region"))).first()
            name = request.POST.get("name", "").strip()[:150]
            if not (region and name):
                messages.error(request, "Viloyat va nom kerak.")
                return redirect("panel:markets")
            data = {
                "region": region,
                "name": name,
                "address": request.POST.get("address", "").strip()[:300],
                "latitude": _f(request.POST.get("latitude"), 90),
                "longitude": _f(request.POST.get("longitude"), 180),
            }
            mid = _pk(request.POST.get("market_id"))
            dup = Market.objects.filter(region=region, name__iexact=name).exclude(pk=mid)
            if dup.exists():
                messages.error(request, f"«{name}» bozori bu viloyatda allaqachon bor.")
                return redirect("panel:markets")
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
    from django.db.models import Prefetch

    shops = list(
        market.shops.select_related("category", "row").prefetch_related(
            Prefetch("staff", queryset=User.objects.order_by("pk"))
        )
    )
    # Raqamli tartib: "2" "10" dan oldin (satr tartibi emas)
    shops.sort(key=lambda s: (0, int(s.number)) if s.number.isdigit() else (1, s.number))
    rows = []
    for s in shops:
        # .first() prefetch keshini chetlab har do'konga alohida so'rov yuborardi (N+1) —
        # oldindan yuklangan ro'yxatdan olamiz
        staff = s.staff.all()
        rows.append({"shop": s, "seller": staff[0] if staff else None})
    return render(request, "panel/market_detail.html", {"market": market, "rows": rows})


WEEKDAYS = [(0, "Du"), (1, "Se"), (2, "Ch"), (3, "Pa"), (4, "Ju"), (5, "Sh"), (6, "Ya")]


@superadmin_required
def shop_edit(request, pk):
    """Do'kon ma'lumotini tahrirlash (egasi, STIR, telefon, tur, qator, dam kunlari)."""
    shop = get_object_or_404(Shop.objects.select_related("market", "category", "row"), pk=pk)
    if request.method == "POST":
        p = request.POST
        owner = p.get("owner_name", "").strip()[:200]
        stir = "".join(c for c in p.get("stir", "") if c.isdigit())[:15]
        number = p.get("number", "").strip()[:20]
        category = ShopCategory.objects.filter(pk=_pk(p.get("category"))).first()
        errors = []
        if not owner:
            errors.append("Egasining F.I.O.")
        if not stir:
            errors.append("STIR")
        if not number:
            errors.append("do'kon raqami")
        if category is None:
            errors.append("savdo turi")
        if errors:
            messages.error(request, "To'ldiring: " + ", ".join(errors) + ".")
            return redirect("panel:shop_edit", pk=shop.pk)
        if Shop.objects.filter(market=shop.market, number=number).exclude(pk=shop.pk).exists():
            messages.error(request, f"№{number} bu bozorda band — boshqa raqam tanlang.")
            return redirect("panel:shop_edit", pk=shop.pk)
        shop.owner_name = owner
        shop.stir = stir
        shop.number = number
        shop.category = category
        owner_phone = clean_phone(p.get("owner_phone"))
        if owner_phone is None:
            messages.error(request, PHONE_ERROR)
            return redirect("panel:shop_edit", pk=shop.pk)
        shop.owner_phone = owner_phone
        shop.address = p.get("address", "").strip()[:300]
        fiscal = p.get("fiscal_id", "").strip().upper()[:40]
        if fiscal and Shop.objects.filter(fiscal_id=fiscal).exclude(pk=shop.pk).exists():
            messages.error(request, f"Kassa raqami {fiscal} boshqa do'konga biriktirilgan.")
            return redirect("panel:shop_edit", pk=shop.pk)
        shop.fiscal_id = fiscal
        shop.row = Row.objects.filter(pk=_pk(p.get("row")), market=shop.market).first()
        days = sorted({int(d) for d in p.getlist("closed") if d.isdigit() and 0 <= int(d) <= 6})
        shop.closed_weekdays = ",".join(str(d) for d in days)
        shop.is_active = p.get("is_active") == "on"
        shop.save()
        request.audit_detail = f"Do'kon №{shop.number} tahrirlandi (STIR {shop.stir})"
        messages.success(request, f"Do'kon №{shop.number} saqlandi.")
        return redirect("panel:market_detail", pk=shop.market_id)
    return render(
        request,
        "panel/shop_edit.html",
        {
            "shop": shop,
            "categories": ShopCategory.objects.all(),
            "rows": shop.market.rows.all(),
            "weekdays": WEEKDAYS,
            "closed": shop.closed_weekday_list(),
            "sellers": shop.staff.all(),
        },
    )


@superadmin_required
def user_edit(request, pk):
    """Foydalanuvchi: F.I.O., telefon; inspektorga bozor biriktirish."""
    u = get_object_or_404(User.objects.select_related("shop", "shop__market"), pk=pk)
    if request.method == "POST":
        full = request.POST.get("full_name", "").split()
        if not full:
            messages.error(request, "F.I.O. ni yozing.")
            return redirect("panel:user_edit", pk=u.pk)
        u.first_name = full[0][:150]
        u.last_name = " ".join(full[1:])[:150]
        phone = clean_phone(request.POST.get("phone"))
        if phone is None:
            messages.error(request, PHONE_ERROR)
            return redirect("panel:user_edit", pk=u.pk)
        u.phone = phone
        tg = request.POST.get("telegram_id", "").strip()
        if tg and not tg.lstrip("-").isdigit():
            messages.error(request, "Telegram ID faqat raqam bo'lsin.")
            return redirect("panel:user_edit", pk=u.pk)
        u.telegram_id = tg[:40]
        u.save(update_fields=["first_name", "last_name", "phone", "telegram_id"])
        if u.is_monitor:
            ids = request.POST.getlist("markets")
            markets = list(Market.objects.filter(pk__in=[_pk(x) for x in ids]))
            if not markets and u.is_inspector:
                messages.warning(
                    request, "Inspektorga bozor biriktirilmadi — u hech bir do'konni ko'rmaydi."
                )
            u.assigned_markets.set(markets)
        messages.success(request, f"{u.get_full_name()} saqlandi.")
        return redirect("panel:users")
    return render(
        request,
        "panel/user_edit.html",
        {
            "u": u,
            "markets": Market.objects.select_related("region"),
            "assigned": set(u.assigned_markets.values_list("pk", flat=True)),
        },
    )


def _add_shop_category(request):
    """Yangi savdo turi + uning mahsulot turlari (kamida 1 — MAJBURIY). Mahsulot turisiz savdo turi
    sotuvchiga bo'sh ro'yxat berardi. Saqlangach — o'sha tur filtrlangan "Mahsulot turlari" sahifasiga
    (birlik va variantni tekshirish uchun)."""
    from django.db import transaction

    from apps.catalog.models import ProductCategory, Unit

    name = " ".join(request.POST.get("name", "").split())[:120]
    items = []
    for raw in request.POST.get("product_types", "").replace(";", ",").replace("\n", ",").split(","):
        n = " ".join(raw.split())[:120]
        if n and n.lower() not in {x.lower() for x in items}:
            items.append(n)
    unit = request.POST.get("default_unit") if request.POST.get("default_unit") in Unit.values else Unit.PIECE
    if not name:
        messages.error(request, "Savdo turi nomini yozing.")
        return redirect("panel:categories")
    if ShopCategory.objects.filter(name__iexact=name).exists():
        messages.error(request, f"«{name}» savdo turi allaqachon bor.")
        return redirect("panel:categories")
    if not items:
        messages.error(request, "Kamida bitta mahsulot turini yozing (masalan: Guruch, Mosh).")
        return redirect("panel:categories")
    busy = {c.name.lower(): c for c in ProductCategory.objects.filter(
        name__in=items).select_related("shop_category")}
    # Nomi band (boshqa savdo turida) — ikki marta qo'shilmaydi; hammasi band bo'lsa — rad
    fresh = [n for n in items if n.lower() not in busy or busy[n.lower()].shop_category_id is None]
    if not fresh:
        messages.error(request, "Bu mahsulot turlari boshqa savdo turlarida bor: "
                                + ", ".join(f"{c.name} ({c.shop_category.name})" for c in busy.values()
                                            if c.shop_category_id) + ". Yangi nom yozing.")
        return redirect("panel:categories")
    with transaction.atomic():
        sc = ShopCategory.objects.create(name=name)
        for n in fresh:
            pc = busy.get(n.lower())
            if pc is not None:  # egasiz eski tur — shu savdo turiga biriktiriladi
                pc.shop_category = sc
                pc.save(update_fields=["shop_category"])
            else:  # variant turi va chirish me'yori nomidan taxmin qilinadi (keyin tahrirlanadi)
                ProductCategory.objects.create(name=n, shop_category=sc, default_unit=unit)
    skipped = [c.name for c in busy.values() if c.shop_category_id and c.name.lower() not in
               {f.lower() for f in fresh}]
    request.audit_detail = f"Savdo turi: {name} ({len(fresh)} mahsulot turi)"
    messages.success(request, f"«{name}» qo'shildi, {len(fresh)} ta mahsulot turi bilan. Birlik va "
                              "variantlarini tekshiring, kerak bo'lsa yana qo'shing.")
    if skipped:
        messages.warning(request, "Boshqa savdo turida bor, qo'shilmadi: " + ", ".join(skipped))
    return redirect(f"{reverse('panel:product_categories')}?turi={sc.pk}")


@superadmin_required
def categories(request):
    """Savdo turlari (ShopCategory) — qo'shish/o'chirish."""
    if request.method == "POST":
        act = request.POST.get("action")
        if act == "add":
            return _add_shop_category(request)
        elif act == "ratio":
            # Kamera bahosi uchun xaridor ulushi (bo'sh — umumiy sozlama)
            cat = ShopCategory.objects.filter(pk=_pk(request.POST.get("id"))).first()
            raw = (request.POST.get("buyer_ratio") or "").strip().replace(",", ".")
            try:
                val = Decimal(raw).quantize(Decimal("0.01")) if raw else None
            except InvalidOperation:
                val = Decimal("-1")
            if cat is None:
                messages.error(request, "Savdo turi topilmadi.")
            elif val is not None and not (Decimal("0.05") <= val <= 1):
                messages.error(request, "Xaridor ulushi 0,05 dan 1 gacha bo'lsin (masalan 0,3).")
            else:
                old_val = cat.buyer_ratio
                cat.buyer_ratio = val
                cat.save(update_fields=["buyer_ratio"])
                request.audit_detail = f"{cat.name}: xaridor ulushi {old_val or '—'} → {val or 'umumiy'}"
                messages.success(request, f"«{cat.name}»: xaridor ulushi saqlandi. Rostlik keyingi "
                                          "hisoblashda yangilanadi.")
        elif act == "delete":
            cat = ShopCategory.objects.filter(pk=_pk(request.POST.get("id"))).first()
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

    from apps.analytics.scoring.services import suggested_buyer_ratios

    suggest = suggested_buyer_ratios()
    cats = list(ShopCategory.objects.annotate(
        nshops=Count("shops", distinct=True), nprod=Count("product_categories", distinct=True)))
    for c in cats:
        c.suggest = suggest.get(c.pk)
    from apps.catalog.models import Unit

    return render(
        request,
        "panel/categories.html",
        {"categories": cats, "global_ratio": SystemSettings.get_solo().buyer_ratio,
         "units": Unit.choices},
    )


def _product_category_fields(request, cat=None):
    """Formadan mahsulot turi maydonlari (xato bo'lsa — matn qaytadi)."""
    from apps.catalog import variants
    from apps.catalog.models import ProductCategory, Unit, VariantKind

    name = " ".join(request.POST.get("name", "").split())[:120]
    if not name:
        return None, "Mahsulot turi nomini yozing."
    dup = ProductCategory.objects.filter(name__iexact=name)
    if cat is not None:
        dup = dup.exclude(pk=cat.pk)
    if dup.exists():
        return None, f"«{name}» mahsulot turi allaqachon bor."
    kind = request.POST.get("variant_kind", "")
    if kind not in VariantKind.values:
        kind = VariantKind.NONE
    unit = request.POST.get("default_unit", "")
    if unit not in Unit.values:
        unit = Unit.PIECE
    opts = [variants.normalize(x, kind) for x in variants.split_list(request.POST.get("variant_options"))]
    if kind in variants.PACKS and any(not variants.measure(o) for o in opts):
        return None, "Qadoq qiymatlari og'irlik yoki hajm bo'lsin: 250 g, 1 kg, 0,5 L."
    if kind in ("none", "color"):
        opts = []  # o'lchamsiz turda tayyor qiymat ma'nosiz
    try:
        waste = Decimal(str(request.POST.get("waste_norm_percent") or "5").replace(",", "."))
    except InvalidOperation:
        waste = Decimal("5")
    shop_cat = ShopCategory.objects.filter(pk=_pk(request.POST.get("shop_category"))).first()
    return {"name": name, "variant_kind": kind, "default_unit": unit, "shop_category": shop_cat,
            "variant_options": ", ".join(dict.fromkeys(opts))[:300],
            "waste_norm_percent": min(max(waste, Decimal("0")), Decimal("100"))}, ""


@superadmin_required
def product_categories(request):
    """Mahsulot turlari: birlik va VARIANT TURI (choy — qadoq, poyabzal — 35–46, guruch — yo'q).

    Sotuvchining "Yangi mahsulot" oynasi shu yerdagi turga qarab faqat mos variantlarni taklif qiladi.
    """
    from django.db.models import Count

    from apps.catalog import variants
    from apps.catalog.models import ProductCategory, Unit, VariantKind

    if request.method == "POST":
        act = request.POST.get("action")
        back = redirect(f"{request.path}?{request.GET.urlencode()}" if request.GET else request.path)
        if act in ("add", "edit"):
            cat = None
            if act == "edit":
                cat = ProductCategory.objects.filter(pk=_pk(request.POST.get("id"))).first()
                if cat is None:
                    messages.error(request, "Mahsulot turi topilmadi.")
                    return back
            fields, err = _product_category_fields(request, cat)
            if err:
                messages.error(request, err)
                return back
            if cat is None:
                cat = ProductCategory(**fields)
                cat.kind_explicit = True  # admin tanlovi — nomidan taxmin qilinmaydi
                cat.save()
                messages.success(request, f"«{cat.name}» qo'shildi.")
            else:
                for k, v in fields.items():
                    setattr(cat, k, v)
                cat.save()
                messages.success(request, f"«{cat.name}» saqlandi.")
            request.audit_detail = (f"Mahsulot turi: {cat.name} — {cat.get_variant_kind_display()}"
                                    f"{' (' + cat.variant_options + ')' if cat.variant_options else ''}")
        elif act == "delete":
            cat = ProductCategory.objects.filter(pk=_pk(request.POST.get("id"))).first()
            if cat is None:
                messages.error(request, "Mahsulot turi topilmadi.")
            elif cat.products.exists() or cat.market_prices.exists():
                messages.error(request, f"«{cat.name}» ishlatilmoqda ({cat.products.count()} mahsulot) — "
                                        "o'chirib bo'lmaydi.")
            else:
                cat.delete()
                messages.success(request, "O'chirildi.")
        return back

    qs = (ProductCategory.objects.select_related("shop_category")
          .annotate(nprod=Count("products", distinct=True)).order_by("shop_category__name", "name"))
    shop_cat = ShopCategory.objects.filter(pk=_pk(request.GET.get("turi"))).first()
    if shop_cat:
        qs = qs.filter(shop_category=shop_cat)
    kind = request.GET.get("variant", "")
    if kind in VariantKind.values:
        qs = qs.filter(variant_kind=kind)
    cats = list(qs)
    for c in cats:
        c.preview = [x for g in variants.spec(c)["presets"].values() for x in g][:8]
    return render(request, "panel/product_categories.html", {
        "cats": cats, "shop_cats": ShopCategory.objects.all(), "shop_cat": shop_cat,
        "kind": kind, "kinds": VariantKind.choices, "units": Unit.choices,
        # Admin tanlaganda sotuvchi formasida nima chiqishini oldindan ko'rsatish uchun
        "kinds_json": {k: {"noun": v["noun"], "colors": v["colors"],
                           "presets": [x for g in v["presets"].values() for x in g][:10]}
                       for k, v in variants.KINDS.items()},
    })


@superadmin_required
def cameras(request):
    """Kameralar boshqaruvi — qo'shish, token ko'rish (django-adminsiz)."""
    from apps.cameras.models import Camera

    if request.method == "POST":
        act = request.POST.get("action")
        if act == "add":
            market = Market.objects.filter(pk=_pk(request.POST.get("market"))).first()
            if not market:
                messages.error(request, "Bozorni tanlang.")
                return redirect("panel:cameras")
            shop = None
            if request.POST.get("shop"):
                # Do'kon SHU bozorniki bo'lsin (boshqa bozor do'koniga hodisa yozilmasin)
                shop = Shop.objects.filter(pk=_pk(request.POST.get("shop")), market=market).first()
                if shop is None:
                    messages.error(request, "Tanlangan do'kon bu bozorda emas.")
                    return redirect("panel:cameras")
            kind = request.POST.get("kind", "")
            if kind not in Camera.Kind.values:
                kind = Camera.Kind.values[0]
            Camera.objects.create(
                name=request.POST.get("name", "").strip()[:120] or "Kamera",
                market=market,
                shop=shop,
                kind=kind,
                rtsp_sub=request.POST.get("rtsp_sub", "").strip()[:500],
            )
            messages.success(request, "Kamera qo'shildi. Token ro'yxatda ko'rinadi.")
        elif act == "toggle":
            cam = Camera.objects.filter(pk=_pk(request.POST.get("id"))).first()
            if cam:
                cam.is_active = not cam.is_active
                cam.save(update_fields=["is_active"])
        elif act == "rotate":
            # Token sizib chiqsa — yangisi beriladi, eskisi darhol ishlamay qoladi
            from apps.cameras.models import make_token

            cam = Camera.objects.filter(pk=_pk(request.POST.get("id"))).first()
            if cam:
                cam.token = make_token()
                cam.save(update_fields=["token"])
                messages.success(request, f"{cam.name}: yangi token berildi. Worker'ga yozing.")
        elif act == "delete":
            cam = Camera.objects.filter(pk=_pk(request.POST.get("id"))).first()
            if cam and cam.events.exists():
                # Hodisalar — dalil va o'tgan kunlar balli. O'chsa tarix o'zgarib ketardi.
                messages.error(
                    request, "Kamera hodisalari bor — o'chirib bo'lmaydi. Faolsizlantiring."
                )
            elif cam:
                cam.delete()
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
