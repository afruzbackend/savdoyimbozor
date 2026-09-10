from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "assigned_market", "assigned_shop", "is_active")
    list_filter = ("role", "assigned_market", "is_active")
    search_fields = ("username", "first_name", "last_name", "phone")
    fieldsets = UserAdmin.fieldsets + (
        ("Rol va biriktirish", {
            "fields": ("role", "phone", "language", "telegram_chat_id",
                       "assigned_market", "assigned_shop"),
        }),
    )
