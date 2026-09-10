def user_role(request):
    """Shablonlarda rolni qulay tekshirish uchun."""
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return {}
    return {
        "is_manager": u.is_manager,
        "is_inspector": u.is_inspector,
        "is_seller": u.is_seller,
    }
