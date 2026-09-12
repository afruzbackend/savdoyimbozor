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
        p1 = request.POST.get("password1") or ""
        p2 = request.POST.get("password2") or ""
        if len(p1) < 6:
            messages.error(request, "Parol kamida 6 belgidan iborat bo'lsin.")
        elif p1 != p2:
            messages.error(request, "Parollar mos kelmadi.")
        else:
            request.user.set_password(p1)
            request.user.must_change_password = False
            request.user.save(update_fields=["password", "must_change_password"])
            update_session_auth_hash(request, request.user)
            messages.success(request, "Parol yangilandi.")
            return redirect(_home_url_for(request))
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
        return redirect("account_settings")
    return render(
        request,
        "registration/settings.html",
        {"base_template": _iface_base(request)},
    )
