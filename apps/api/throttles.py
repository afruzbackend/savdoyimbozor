"""API so'rov chegaralari."""

from __future__ import annotations

import hashlib

from rest_framework.throttling import SimpleRateThrottle


class CameraRateThrottle(SimpleRateThrottle):
    """Kamera worker'i — o'z tokeni bo'yicha (IP emas: bozordagi o'nlab kamera bitta NAT ortida,
    IP bo'yicha cheklansa bir-birini to'sib qo'yardi). Token keshda xesh ko'rinishida saqlanadi."""

    scope = "camera"

    def get_cache_key(self, request, view):
        token = request.headers.get("X-Camera-Token", "")
        ident = (
            hashlib.sha256(token.encode()).hexdigest()[:32] if token else self.get_ident(request)
        )
        return self.cache_format % {"scope": self.scope, "ident": ident}
