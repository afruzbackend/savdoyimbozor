"""Auth oqimi: blokli login, birinchi kirishda parol almashtirish, profil."""

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


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_home_url_for(request))

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        settings_obj = SystemSettings.get_solo()

        user = User.objects.filter(username__iexact=username).first()
        if user and user.is_locked:
            messages.error(request, "Hisob vaqtincha bloklangan. Birozdan so'ng urinib ko'ring.")
            return render(request, "registration/login.html", {"username": username})

        auth_user = authenticate(request, username=username, password=password)
        if auth_user is None and user and not user.is_active and user.check_password(password):
            # Parol to'g'ri, lekin admin bloklagan — "parol noto'g'ri" deb chalg'itmaymiz
            messages.error(request, "Hisobingiz bloklangan. Administrator bilan bog'laning.")
            return render(request, "registration/login.html", {"username": username})
        if auth_user is None:
            if user:
                user.register_failed_login(
                    settings_obj.login_max_attempts, settings_obj.login_lock_minutes
                )
            messages.error(request, "Login yoki parol noto'g'ri.")
            return render(request, "registration/login.html", {"username": username})

        auth_user.reset_lockout()
        login(request, auth_user)
        AuditLog.objects.create(
            user=auth_user,
            action=AuditLog.Action.LOGIN,
            path=request.path,
            interface=getattr(request, "interface", ""),
        )
        if auth_user.must_change_password:
            return redirect("password_change")
        return redirect(_home_url_for(request))

    return render(request, "registration/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def password_change(request):
    """Birinchi kirishda majburiy, keyin ixtiyoriy."""
    if request.method == "POST":
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        p1 = request.POST.get("password1") or ""
        p2 = request.POST.get("password2") or ""
        weak = None
        try:
            validate_password(p1, request.user)  # min 6 + keng tarqalgan ("123456") parollar
        except ValidationError:
            weak = True
        if len(p1) < 6:
            messages.error(request, "Parol kamida 6 belgidan iborat bo'lsin.")
        elif p1 != p2:
            messages.error(request, "Parollar mos kelmadi.")
        elif weak:
            messages.error(request, "Parol juda oddiy (masalan 123456) — murakkabroq tanlang.")
        elif request.user.check_password(p1):
            messages.error(request, "Yangi parol eskisi bilan bir xil bo'lmasin.")
        else:
            request.user.set_password_visible(p1)
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
        phone = request.POST.get("phone", "").strip()[:20]
        if phone:
            user.phone = phone
        user.notify_telegram = bool(request.POST.get("notify_telegram"))
        user.save(update_fields=["phone", "notify_telegram"])
        from django.contrib import messages

        messages.success(request, "Sozlamalar saqlandi.")
        return redirect(_safe_next(request, "account_settings"))
    return render(
        request,
        "registration/settings.html",
        {"base_template": _iface_base(request)},
    )
