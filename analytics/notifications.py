"""Telegram ogohlantirish. Qizil signal chiqqanda inspektorga xabar yuboradi.

Yangi kutubxona kerak emas (urllib). `TELEGRAM_BOT_TOKEN` sozlanmagan bo'lsa yoki
inspektorda `telegram_chat_id` yo'q bo'lsa — jimgina o'tadi (xatolik bermaydi).
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def send_telegram(chat_id: str, text: str) -> bool:
    """Bitta xabar yuboradi. Muvaffaqiyatli bo'lsa True."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("Telegram xabar yuborilmadi: %s", e)
        return False


def notify_alert(alert) -> bool:
    """Signal bo'yicha biriktirilgan inspektorga xabar yuboradi."""
    inspector = alert.assigned_to
    if not inspector or not getattr(inspector, "telegram_chat_id", ""):
        return False
    emoji = "🔴" if alert.level == "red" else "🟡"
    text = (f"{emoji} <b>Yangi signal</b>\n"
            f"Do'kon: <b>{alert.shop.name}</b>\n"
            f"Bozor: {alert.shop.market.name}\n"
            f"Sabab: {alert.message}\n"
            f"Sana: {alert.date}")
    ok = send_telegram(inspector.telegram_chat_id, text)
    if ok:
        alert.telegram_sent = True
        alert.save(update_fields=["telegram_sent"])
    return ok
