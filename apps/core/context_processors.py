import time

from django.conf import settings

# Statik fayllar versiyasi — kesh-buster. Har server ishga tushganda yangilanadi (dev);
# prod'da ManifestStaticFilesStorage o'zi hashlaydi, lekin bu ham zarar qilmaydi.
ASSET_V = str(int(time.time()))


def ui_context(request):
    """Shablonlar uchun umumiy kontekst: interfeys, tema, rol."""
    user = getattr(request, "user", None)
    # Faqat 2 rejim: yorug' (default) yoki qorong'i. "Tizim" rejimi yo'q.
    theme = request.COOKIES.get("theme") or "light"
    if theme not in ("light", "dark"):
        theme = "light"
    ctx = {
        "interface": getattr(request, "interface", "inspector"),
        "theme": theme,  # "light" | "dark"
        "uilang": request.COOKIES.get("uilang", ""),  # "" lotin / "cyrl" kirill
        "asset_v": ASSET_V,
        # Xodim uchun faolsizlik chegarasi (ms) — liveRefresh shundan keyin sahifani yangilamaydi
        "idle_ms": (settings.STAFF_IDLE_MINUTES * 60_000
                    if user and user.is_authenticated and getattr(user, "is_staff_role", False) else 0),
        # Telegram bot sozlanmagan bo'lsa — sozlamalarda foydasiz tugma ko'rsatilmaydi
        "telegram_enabled": bool(getattr(settings, "TELEGRAM_BOT_TOKEN", "")),
    }
    if user and user.is_authenticated:
        ctx["current_role"] = getattr(user, "role", "")
        if ctx["current_role"] == "seller":
            try:  # 20:00 eslatmasi Celery beat'siz ham (kuniga bir marta)
                from apps.sales.management.commands.close_reminders import remind_if_due

                remind_if_due(user)
                from apps.sales.services.debts import debt_reminders

                debt_reminders(user, getattr(user, "shop", None))
            except Exception:  # noqa: BLE001 — sahifa ochilishini buzmasin
                pass
        try:
            ctx["unread_notifications"] = user.notifications.filter(is_read=False).count()
        except Exception:
            ctx["unread_notifications"] = 0
        attention = ctx["unread_notifications"]
        ctx["readonly"] = ctx["current_role"] == "prosecutor"
        if ctx["current_role"] in ("inspector", "prosecutor"):
            # Menyuda ko'rinadigan son: yangi signal va javobsiz e'tiroz (ilova ichida xabar)
            from apps.analytics.models import Alert, Appeal

            shops = user.visible_shops()
            ctx["nav_alerts_new"] = Alert.objects.filter(
                shop__in=shops, status=Alert.Status.NEW, level__in=("red", "yellow")
            ).count()
            ctx["nav_appeals_new"] = Appeal.objects.filter(
                shop__in=shops, status=Appeal.Status.NEW
            ).count()
            attention += ctx["nav_alerts_new"] + ctx["nav_appeals_new"]
        ctx["nav_attention"] = attention
    return ctx
