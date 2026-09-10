from .models import AuditLog

# Yozib boriladigan muhim yo'llar (POST'lar va hisobot/eksport ko'rishlari)
AUDITED_PREFIXES = ("/reports/", "/analytics/declarations/", "/inspections/new")


class AuditMiddleware:
    """Muhim amallarni audit jurnaliga yozadi. Statik/media so'rovlar tashlanadi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._maybe_log(request, response)
        except Exception:
            pass  # audit hech qachon asosiy oqimni buzmasin
        return response

    def _maybe_log(self, request, response):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return
        path = request.path
        is_post = request.method == "POST"
        is_audited_get = any(path.startswith(p) for p in AUDITED_PREFIXES)
        if not (is_post or is_audited_get):
            return
        if path.startswith(("/static/", "/media/", "/admin/jsi18n")):
            return
        AuditLog.objects.create(
            user=user,
            method=request.method,
            path=path[:300],
            ip=self._client_ip(request),
        )

    @staticmethod
    def _client_ip(request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
