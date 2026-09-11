from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import translation
from django.views.decorators.http import require_POST


@require_POST
def set_theme(request):
    """Tema tanlovini cookie'ga saqlaydi: light / dark / '' (tizim)."""
    theme = request.POST.get("theme", "")
    if theme not in ("light", "dark", ""):
        theme = ""
    resp = JsonResponse({"theme": theme}) if request.htmx else redirect(
        request.META.get("HTTP_REFERER", "/"))
    resp.set_cookie("theme", theme, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@require_POST
def set_language(request):
    """Til tanlovini saqlaydi."""
    lang = request.POST.get("language", "uz")
    if lang not in dict(__import__("django.conf", fromlist=["settings"]).settings.LANGUAGES):
        lang = "uz"
    translation.activate(lang if lang != "uz-cyrl" else "uz")
    resp = redirect(request.META.get("HTTP_REFERER", "/"))
    resp.set_cookie("django_language", lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
    if request.user.is_authenticated:
        request.user.language = lang
        request.user.save(update_fields=["language"])
    return resp


@login_required
def styleguide(request):
    """Dizayn tizimi ko'rgazmasi — barcha komponentlar bir sahifada (P1)."""
    return render(request, "components/styleguide.html")


def healthz(request):
    return HttpResponse("ok")


@login_required
def panel_home(request):
    """Super admin bosh sahifasi (P4'da to'ldiriladi)."""
    return render(request, "panel/home.html")
