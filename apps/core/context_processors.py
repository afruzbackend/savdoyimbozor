def ui_context(request):
    """Shablonlar uchun umumiy kontekst: interfeys, tema, rol."""
    user = getattr(request, "user", None)
    theme = request.COOKIES.get("theme", "")
    ctx = {
        "interface": getattr(request, "interface", "inspector"),
        "theme": theme,  # "", "light", "dark" — bo'sh bo'lsa tizim afzalligi
        "uilang": request.COOKIES.get("uilang", ""),  # "" lotin / "cyrl" kirill
    }
    if user and user.is_authenticated:
        ctx["current_role"] = getattr(user, "role", "")
    return ctx
