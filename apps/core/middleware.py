"""Rol-based routing va audit middleware."""

from __future__ import annotations

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

# Rol → o'ziga tegishli interfeys (urlconf tanlash uchun)
ROLE_INTERFACE = {
    "superadmin": "panel",
    "inspector": "inspector",
    "seller": "seller",
}


class HostRoutingMiddleware(MiddlewareMixin):
    """BITTA host — foydalanuvchi ROLIga qarab ROOT_URLCONF tanlaydi.

    Sotuvchi, nazoratchi va admin hammasi bitta manzilda (localhost). Kim
    kirsa — o'z roli interfeysini ko'radi. Ro'yxatdan o'tish yo'q: loginni
    admin beradi. Kirmaganlar login sahifasini ko'radi (standart urlconf).

    XAVFSIZLIK: har rol faqat o'z urlconf'iga ega bo'lgani uchun boshqa rol
    sahifalariga URL yo'q — ruxsat cheklovi avtomatik (masalan sotuvchi
    nazorat dashboardiga hech qanday yo'l bilan kira olmaydi → 404).
    """

    def process_request(self, request):
        user = getattr(request, "user", None)
        # Standart: inspector urlconf (login/logout/api shu yerda ham bor).
        interface = "inspector"
        if user is not None and user.is_authenticated:
            interface = ROLE_INTERFACE.get(getattr(user, "role", ""), "inspector")
        request.urlconf = settings.HOST_URLCONF[interface]
        request.interface = interface
        return None


class AuditMiddleware(MiddlewareMixin):
    """Muhim amallarni audit jurnaliga yozadi (POST va eksport ko'rishlari)."""

    AUDITED_GET_PREFIXES = ("/reports/export", "/api/reports/export")

    def process_response(self, request, response):
        try:
            self._log(request, response)
        except Exception:
            pass  # audit asosiy oqimni buzmasin
        return response

    def _log(self, request, response):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return
        path = request.path
        if path.startswith(("/static/", "/media/", "/prefs/")):
            return
        is_post = request.method == "POST"
        is_export = any(path.startswith(p) for p in self.AUDITED_GET_PREFIXES)
        if not (is_post or is_export):
            return
        from .models import AuditLog

        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.EXPORT if is_export else AuditLog.Action.WRITE,
            method=request.method,
            path=path[:300],
            ip=self._ip(request),
            interface=getattr(request, "interface", ""),
        )

    @staticmethod
    def _ip(request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
