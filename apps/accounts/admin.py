from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "shop", "is_shop_owner", "is_active")
    list_filter = ("role", "is_active", "is_shop_owner")
    search_fields = ("username", "first_name", "last_name", "phone")
    filter_horizontal = UserAdmin.filter_horizontal + ("assigned_markets",)
    fieldsets = UserAdmin.fieldsets + (
        (_ := "Rol va biriktirish", {
            "fields": ("role", "phone", "language", "telegram_id",
                       "shop", "is_shop_owner", "assigned_markets",
                       "must_change_password"),
        }),
    )
