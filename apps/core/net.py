"""Mijoz IP manzili — audit jurnali va suiiste'mol cheklovlari uchun YAGONA manba."""

from django.conf import settings


def client_ip(request) -> str:
    """Soxtalashtirib bo'lmaydigan IP.

    X-Forwarded-For ning BIRINCHI qiymatini mijozning o'zi yozishi mumkin (nginx
    $proxy_add_x_forwarded_for uni saqlab, oxiriga qo'shadi) — ishlatilmaydi.
    Proksi ortida (BEHIND_PROXY=True): nginx X-Real-IP ni $remote_addr bilan ALMASHTIRADI;
    u yo'q bo'lsa XFF ning OXIRGI qiymati (bizning proksi qo'shgani). Aks holda REMOTE_ADDR.
    """
    meta = request.META
    if getattr(settings, "BEHIND_PROXY", False):
        real = meta.get("HTTP_X_REAL_IP", "").strip()
        if real:
            return real[:45]
        xff = meta.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            return xff.split(",")[-1].strip()[:45]
    return (meta.get("REMOTE_ADDR") or "")[:45]
