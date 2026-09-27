"""Auth oqimi: blokli login (IP + hisob), ikki bosqichli himoya, parol almashtirish, profil."""

import time

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.core.models import AuditLog, SystemSettings

from .models import User


def _home_url_for(request):
    """Rol/interfeysga qarab bosh sahifa."""
    return "/"


def _safe_next(request, fallback):
    """POST'dagi `next` faqat xavfsiz ichki (nisbiy) yo'l bo'lsa qaytariladi."""
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return fallback


def _audit_login(request, user, detail):
    """Kirish urinishi audit jurnaliga: IP, rol interfeysi va natija bilan."""
    from apps.core.middleware import ROLE_INTERFACE, AuditMiddleware

    iface = ""
    if user is not None:
        iface = "panel" if user.is_superadmin else ROLE_INTERFACE.get(user.role, "")
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.LOGIN,
        path=request.path,
        ip=AuditMiddleware._ip(request),
        interface=iface,
        detail=detail[:300],
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_home_url_for(request))

    if request.method == "POST":
        from apps.core.net import client_ip

        from . import throttle

        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        settings_obj = SystemSettings.get_solo()
        ip = client_ip(request)

        user = User.objects.filter(username__iexact=username).first()
        if throttle.ip_blocked(ip):
            # Parol umuman tekshirilmaydi — terib topish hujumi to'xtaydi
            _audit_login(request, user, f"Rad: IP bloklangan (login: {username[:40]})")
            messages.error(request, "Bu qurilmadan juda ko'p xato urinish bo'ldi. "
                                    "Birozdan so'ng urinib ko'ring.")
            return render(request, "registration/login.html", {"username": username})
        if user and (user.is_locked or throttle.pair_blocked(user, ip)):
            _audit_login(request, user, "Rad: vaqtincha bloklangan hisobga urinish")
            messages.error(request, "Hisob vaqtincha bloklangan. Birozdan so'ng urinib ko'ring.")
            return render(request, "registration/login.html", {"username": username})

        auth_user = authenticate(request, username=username, password=password)
        if auth_user is None and user and not user.is_active and user.check_password(password):
            # Parol to'g'ri, lekin admin bloklagan — "parol noto'g'ri" deb chalg'itmaymiz
            _audit_login(request, user, "Rad: admin bloklagan hisob")
            messages.error(request, "Hisobingiz bloklangan. Administrator bilan bog'laning.")
            return render(request, "registration/login.html", {"username": username})
        if auth_user is None:
            throttle.register_failure(ip, user, settings_obj)
            # Muvaffaqiyatsiz urinish ham yoziladi (parol terish hujumini ko'rish uchun)
            _audit_login(request, user, f"Xato parol (login: {username[:40]})")
            messages.error(request, "Login yoki parol noto'g'ri.")
            return render(request, "registration/login.html", {"username": username})

        throttle.register_success(ip, auth_user)
        if auth_user.totp_enabled:
            # Parol to'g'ri — endi ilovadagi 6 xonali kod (sessiya hali ochilmaydi)
            request.session["2fa_uid"] = auth_user.pk
            request.session["2fa_at"] = int(time.time())
            request.session["2fa_tries"] = 0
            return redirect("login_2fa")
        login(request, auth_user)
        _audit_login(request, auth_user, "Muvaffaqiyatli kirish")
        if auth_user.must_change_password:
            return redirect("password_change")
        return redirect(_home_url_for(request))

    if request.GET.get("timeout"):
        messages.info(request, "Uzoq vaqt faollik bo'lmagani uchun xavfsizlik maqsadida tizimdan "
                               "chiqildi. Qaytadan kiring.")
    return render(request, "registration/login.html")


TWOFA_TTL = 5 * 60  # parol kiritilgandan keyin kod uchun vaqt
TWOFA_TRIES = 5


def login_2fa(request):
    """Ikkinchi bosqich: ilova kodi yoki zaxira kod."""
    from apps.core.net import client_ip

    from . import throttle, totp

    uid = request.session.get("2fa_uid")
    started = request.session.get("2fa_at", 0)
    user = User.objects.filter(pk=uid, is_active=True).first() if uid else None
    if user is None or time.time() - started > TWOFA_TTL:
        for k in ("2fa_uid", "2fa_at", "2fa_tries"):
            request.session.pop(k, None)
        if uid:
            messages.error(request, "Kod kiritish vaqti tugadi — qaytadan kiring.")
        return redirect("login")
    if request.method == "POST":
        code = request.POST.get("code", "")
        step = totp.verify(user.totp_secret, code, last_step=user.totp_last_step)
        used_backup = step is None and totp.use_backup_code(user, code)
        if step is not None or used_backup:
            if step is not None:
                user.totp_last_step = step
                user.save(update_fields=["totp_last_step"])
            for k in ("2fa_uid", "2fa_at", "2fa_tries"):
                request.session.pop(k, None)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            _audit_login(request, user, "Muvaffaqiyatli kirish (2FA"
                         + (", zaxira kod)" if used_backup else ")"))
            if used_backup:
                left = len(user.backup_codes or [])
                messages.warning(request, f"Zaxira kod ishlatildi — {left} ta qoldi. "
                                          "Telefon topilmasa, yangi zaxira kodlar oling.")
            if user.must_change_password:
                return redirect("password_change")
            return redirect(_home_url_for(request))
        tries = request.session.get("2fa_tries", 0) + 1
        request.session["2fa_tries"] = tries
        throttle.register_failure(client_ip(request), None, SystemSettings.get_solo())
        _audit_login(request, user, "Xato 2FA kodi")
        if tries >= TWOFA_TRIES:
            for k in ("2fa_uid", "2fa_at", "2fa_tries"):
                request.session.pop(k, None)
            messages.error(request, "Kod ko'p marta noto'g'ri kiritildi — qaytadan kiring.")
            return redirect("login")
        messages.error(request, "Kod noto'g'ri. Ilovadagi yangi kodni kiriting.")
    return render(request, "registration/login_2fa.html", {"account": user.username})


@login_required
def twofa_setup(request):
    """Ikki bosqichli himoyani yoqish / o'chirish / zaxira kodlarni yangilash."""
    from . import totp

    user = request.user
    required = user.is_staff_role and SystemSettings.get_solo().require_2fa_staff
    ctx = {"base_template": _iface_base(request), "required": required}
    if request.method == "POST":
        action = request.POST.get("action")
        code = request.POST.get("code", "")
        if action == "enable" and not user.totp_enabled:
            secret = request.session.get("2fa_pending_secret", "")
            step = totp.verify(secret, code)
            if step is None:
                messages.error(request, "Kod noto'g'ri — ilovadagi hozirgi 6 xonali kodni kiriting.")
                return redirect("twofa_setup")
            codes, hashes = totp.new_backup_codes()
            user.totp_secret, user.totp_enabled, user.totp_last_step = secret, True, step
            user.backup_codes = hashes
            user.save(update_fields=["totp_secret", "totp_enabled", "totp_last_step",
                                     "backup_codes"])
            request.session.pop("2fa_pending_secret", None)
            request.audit_detail = "2FA yoqildi"
            messages.success(request, "Ikki bosqichli himoya yoqildi.")
            return render(request, "registration/twofa.html", {**ctx, "backup": codes})
        if action in ("disable", "backup") and user.totp_enabled:
            step = totp.verify(user.totp_secret, code, last_step=user.totp_last_step)
            if step is None:
                messages.error(request, "Kod noto'g'ri.")
                return redirect("twofa_setup")
            user.totp_last_step = step
            if action == "backup":
                codes, user.backup_codes = totp.new_backup_codes()
                user.save(update_fields=["totp_last_step", "backup_codes"])
                request.audit_detail = "2FA zaxira kodlari yangilandi"
                return render(request, "registration/twofa.html", {**ctx, "backup": codes})
            if required:
                messages.error(request, "Sizning rolingiz uchun ikki bosqichli himoya majburiy.")
                return redirect("twofa_setup")
            user.totp_secret, user.totp_enabled, user.backup_codes = "", False, []
            user.save(update_fields=["totp_secret", "totp_enabled", "totp_last_step",
                                     "backup_codes"])
            request.audit_detail = "2FA o'chirildi"
            messages.success(request, "Ikki bosqichli himoya o'chirildi.")
        return redirect("twofa_setup")
    if not user.totp_enabled:
        secret = request.session.get("2fa_pending_secret") or totp.new_secret()
        request.session["2fa_pending_secret"] = secret
        ctx.update(secret=" ".join(secret[i:i + 4] for i in range(0, len(secret), 4)),
                   qr=totp.qr_svg(totp.provisioning_uri(secret, user.username)))
    else:
        ctx["backup_left"] = len(user.backup_codes or [])
    return render(request, "registration/twofa.html", ctx)


def logout_view(request):
    # Faqat POST (CSRF tokeni bilan). GET bilan chiqarilsa, begona sahifadagi <img src="/logout/">
    # ham foydalanuvchini tizimdan chiqarib yuborardi (CSRF logout).
    if request.method != "POST":
        return redirect("/" if request.user.is_authenticated else "login")
    logout(request)
    return redirect("login")


def password_min_length(user) -> int:
    """Xodim (admin/nazoratchi/prokuror) — 12, sotuvchi — 8 belgi."""
    return 12 if getattr(user, "is_staff_role", False) else 8


@login_required
def password_change(request):
    """Birinchi kirishda majburiy, keyin ixtiyoriy."""
    if request.method == "POST":
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        p1 = request.POST.get("password1") or ""
        p2 = request.POST.get("password2") or ""
        weak = None
        min_len = password_min_length(request.user)
        try:
            validate_password(p1, request.user)  # keng tarqalgan, faqat raqam, loginga o'xshash — rad
        except ValidationError:
            weak = True
        if len(p1) < min_len:
            messages.error(request, f"Parol kamida {min_len} belgidan iborat bo'lsin.")
        elif p1 != p2:
            messages.error(request, "Parollar mos kelmadi.")
        elif weak:
            messages.error(request, "Parol juda oddiy (faqat raqam, keng tarqalgan yoki loginga o'xshash) — "
                                    "harf va raqam aralash, murakkabroq tanlang.")
        elif request.user.check_password(p1):
            messages.error(request, "Yangi parol eskisi bilan bir xil bo'lmasin.")
        else:
            request.user.set_own_password(p1)  # faqat xesh — admin ham ko'rmaydi
            request.user.must_change_password = False
            request.user.save(
                update_fields=["password", "visible_password", "must_change_password"]
            )
            update_session_auth_hash(request, request.user)
            messages.success(request, "Parol yangilandi.")
            return redirect(_safe_next(request, _home_url_for(request)))
        # Xato bo'lsa — kelgan sahifaga qaytamiz (modal shu yerda)
        if request.POST.get("next"):
            return redirect(_safe_next(request, _home_url_for(request)))
    return render(
        request, "registration/password_change.html", {"forced": request.user.must_change_password}
    )


@login_required
def _iface_base(request):
    bases = {
        "seller": "seller/base.html",
        "inspector": "inspector/base.html",
        "panel": "panel/base.html",
    }
    return bases.get(getattr(request, "interface", "inspector"), "inspector/base.html")


@login_required
def profile(request):
    return render(request, "registration/profile.html", {"base_template": _iface_base(request)})


@login_required
def account_settings(request):
    """Foydalanuvchi sozlamalari: parol, telefon, bildirishnoma afzalliklari."""
    user = request.user
    if request.method == "POST":
        from apps.core.format import PHONE_ERROR, clean_phone

        phone = clean_phone(request.POST.get("phone"))  # bo'sh qoldirsa — o'chiriladi
        if phone is None:
            messages.error(request, PHONE_ERROR)
            return redirect(_safe_next(request, "account_settings"))
        user.phone = phone
        fields = ["phone"]
        if "telegram_id" in request.POST:  # faqat bot sozlangan bo'lsa formada bor
            tg = request.POST.get("telegram_id", "").strip()
            if tg and not tg.lstrip("-").isdigit():
                messages.error(request, "Telegram ID faqat raqam bo'lsin (botdan oling).")
                return redirect(_safe_next(request, "account_settings"))
            user.telegram_id = tg[:40]
            user.notify_telegram = bool(request.POST.get("notify_telegram"))
            fields += ["telegram_id", "notify_telegram"]
        user.save(update_fields=fields)
        messages.success(request, "Sozlamalar saqlandi.")
        return redirect(_safe_next(request, "account_settings"))
    return render(
        request,
        "registration/settings.html",
        {"base_template": _iface_base(request)},
    )
