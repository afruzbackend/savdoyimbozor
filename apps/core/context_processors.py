import time

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
    }
    if user and user.is_authenticated:
        ctx["current_role"] = getattr(user, "role", "")
    return ctx
