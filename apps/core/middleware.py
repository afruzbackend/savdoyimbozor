"""Rol-based routing va audit middleware."""

from __future__ import annotations

import re

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

# Rol → o'ziga tegishli interfeys (urlconf tanlash uchun)
ROLE_INTERFACE = {
    "superadmin": "panel",
    "inspector": "inspector",
    "prosecutor": "inspector",  # nazorat interfeysi, lekin FAQAT KO'RISH (ReadOnlyRoleMiddleware)
    "seller": "seller",
}


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Content-Security-Policy va Permissions-Policy (Django 5.2 da o'rnatilgan CSP yo'q).

    Barcha aktivlar lokal (CDN yo'q), shuning uchun manba — faqat o'z domeni: XSS topilgan taqdirda
    ham begona skript yuklab bo'lmaydi va ma'lumot begona serverga yuborilmaydi (connect/img/form).
    'unsafe-inline'/'unsafe-eval' — sahifa ichidagi skriptlar va Alpine.js ifodalari uchun.
    """

    def process_response(self, request, response):
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if policy and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = policy
        perms = getattr(settings, "PERMISSIONS_POLICY", "")
        if perms and "Permissions-Policy" not in response:
            response["Permissions-Policy"] = perms
        return response


class IdleTimeoutMiddleware(MiddlewareMixin):
    """Xodim (admin/tekshiruvchi/prokuror) STAFF_IDLE_MINUTES faol bo'lmasa — tizimdan chiqariladi.

    Umumiy kompyuterda (bozor idorasi) qoldirilgan sessiya 2 hafta ochiq turmasin. Sotuvchilarga
    qo'llanmaydi (o'z telefoni, tez sotuv). Sessiyaga har so'rovda emas, daqiqada bir yoziladi.
    Dashboard avto-yangilanishi foydalanuvchi faolligi emas — liveRefresh xodim uzoq qimirlamasa
    to'xtaydi, shuning uchun muddat baribir tugaydi.
    """

    KEY = "idle_last"
    WRITE_EVERY = 60

    def process_request(self, request):
        import time

        limit = getattr(settings, "STAFF_IDLE_MINUTES", 0) * 60
        user = getattr(request, "user", None)
        if not limit or not (user and user.is_authenticated and getattr(user, "is_staff_role", False)):
            return None
        now = int(time.time())
        last = request.session.get(self.KEY)
        if last and now - last > limit:
            from django.contrib.auth import logout

            logout(request)
            if request.path.startswith("/api/") or request.headers.get("HX-Request"):
                from django.http import JsonResponse

                return JsonResponse({"detail": "Sessiya tugadi — qaytadan kiring."}, status=401)
            from urllib.parse import quote

            from django.shortcuts import redirect

            return redirect(f"/login/?timeout=1&next={quote(request.get_full_path(), safe='/')}")
        if not last or now - last >= self.WRITE_EVERY:
            request.session[self.KEY] = now
        return None


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
            if getattr(user, "is_superadmin", False):
                # createsuperuser bilan ochilgan admin (rol standart "seller") ham panelga
                interface = "panel"
            else:
                interface = ROLE_INTERFACE.get(getattr(user, "role", ""), "inspector")
        request.urlconf = settings.HOST_URLCONF[interface]
        request.interface = interface
        return None


class ForcePasswordChangeMiddleware(MiddlewareMixin):
    """Birinchi kirishda (yoki admin parolni tiklagach) parol almashtirish MAJBURIY.

    Ilgari faqat login'dan keyin yo'naltirilardi — "/" ni qo'lda ochib chetlab o'tish mumkin edi.
    """

    ALLOWED = ("/password/change/", "/logout/", "/login/", "/static/", "/prefs/", "/sw.js")

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and getattr(user, "must_change_password", False)):
            return None
        if request.path.startswith(self.ALLOWED):
            return None
        if request.path.startswith("/api/"):
            from django.http import JsonResponse

            return JsonResponse({"detail": "Avval parolni almashtiring."}, status=403)
        from django.shortcuts import redirect

        return redirect("/password/change/")


class ForceTwoFactorMiddleware(MiddlewareMixin):
    """SystemSettings.require_2fa_staff yoqilgan bo'lsa: admin/tekshiruvchi/prokuror ikki bosqichli
    himoyani yoqmaguncha boshqa sahifaga o'tolmaydi (sotuvchilarga majburiy emas)."""

    ALLOWED = ("/profil/2fa/", "/logout/", "/login/", "/password/change/", "/static/", "/prefs/",
               "/sw.js")

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and getattr(user, "is_staff_role", False)):
            return None
        if user.totp_enabled or request.path.startswith(self.ALLOWED):
            return None
        from apps.core.models import SystemSettings

        if not SystemSettings.get_solo().require_2fa_staff:
            return None
        if request.path.startswith("/api/"):
            from django.http import JsonResponse

            return JsonResponse({"detail": "Avval ikki bosqichli himoyani yoqing."}, status=403)
        from django.shortcuts import redirect

        return redirect("/profil/2fa/")


class ReadOnlyRoleMiddleware(MiddlewareMixin):
    """Prokuror (kuzatuvchi) hech narsani o'zgartira olmaydi — server tomonida bloklanadi.

    Faqat shaxsiy amallar ruxsat: chiqish, parol, o'z telefon/sozlamasi, til/mavzu.
    """

    ALLOWED = ("/logout/", "/password/change/", "/profil/sozlamalar/", "/profil/2fa/", "/prefs/",
               "/login/")

    def process_request(self, request):
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and getattr(user, "role", "") == "prosecutor"):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS") or request.path.startswith(self.ALLOWED):
            return None
        from django.shortcuts import render

        return render(request, "403.html", {
            "heading": "Kuzatuvchi rejimi",
            "message": "Sizning hisobingiz faqat ko'rish uchun: ma'lumotni o'zgartirib bo'lmaydi.",
        }, status=403)


class AuditMiddleware(MiddlewareMixin):
    """Muhim amallarni audit jurnaliga yozadi (POST, eksport, dalil ko'rish)."""

    # Inspektor Excel eksporti (ilgari prefiks noto'g'ri edi — eksport yozilmasdi)
    AUDITED_GET_PREFIXES = ("/hisobot/eksport/",)
    # Nazoratchi do'kon ma'lumotini / dalil to'plamini ochgani (kim, qaysi do'kon)
    VIEW_RE = re.compile(r"^/(dokon/\d+/(dalil/)?|tekshiruv/\d+/akt/|hodisalar/\d+/|ombor/dokon/\d+/)$")

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
        # /login/ — login_view o'zi batafsil yozadi (ikki marta yozilmasin)
        if path.startswith(("/static/", "/media/", "/prefs/", "/login/", "/sw.js")):
            return
        is_post = request.method == "POST"
        is_export = request.method == "GET" and any(
            path.startswith(p) for p in self.AUDITED_GET_PREFIXES
        )
        is_view = (
            request.method == "GET"
            and getattr(request, "interface", "") == "inspector"
            and response.status_code == 200
            and (self.VIEW_RE.match(path)
                 # Prokurorning HAR bir sahifa ko'rishi yoziladi (kim nimani ko'rdi)
                 or (getattr(user, "role", "") == "prosecutor"
                     and "text/html" in response.get("Content-Type", "")))
        )
        # View o'zi "buni yoz" desa (masalan hodisa Excel'i) — GET bo'lsa ham yoziladi
        forced = bool(getattr(request, "audit_action", None) or getattr(request, "audit_detail", ""))
        if not (is_post or is_export or is_view or forced):
            return
        from .models import AuditLog

        if getattr(request, "audit_action", None) in AuditLog.Action.values:
            action = request.audit_action  # view aniq tur bergan (masalan sozlama)
        elif is_export:
            action = AuditLog.Action.EXPORT
        elif is_view:
            action = AuditLog.Action.VIEW
        else:
            action = AuditLog.Action.WRITE
        AuditLog.objects.create(
            user=user,
            action=action,
            method=request.method,
            path=path[:300],
            ip=self._ip(request),
            interface=getattr(request, "interface", ""),
            # View o'rnatgan tafsilot: NIMA qilindi (masalan "Signal #12 e'tiborsiz: №5")
            detail=str(getattr(request, "audit_detail", ""))[:300],
        )

    @staticmethod
    def _ip(request):
        from apps.core.net import client_ip

        return client_ip(request) or None
