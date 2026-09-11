"""Host-based routing va audit middleware."""

from __future__ import annotations

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class HostRoutingMiddleware(MiddlewareMixin):
    """Hostga qarab (sotuvchi./nazorat./panel.) ROOT_URLCONF tanlaydi.

    Dev: `sotuvchi.localhost:8000` → seller. Host mos kelmasa — standart (inspector).
    request.interface ga interfeys nomi yoziladi (audit va shablonlar uchun).
    """

    def process_request(self, request):
        host = request.get_host().split(":")[0]  # portsiz
        prefix = host.split(".")[0]
        interface = settings.HOST_PREFIX_MAP.get(prefix)
        if interface:
            request.urlconf = settings.HOST_URLCONF[interface]
            request.interface = interface
        else:
            request.interface = "inspector"  # standart


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
