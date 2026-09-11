from django.contrib import admin

from .models import Shop


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("number", "market", "category", "stir", "owner_name", "is_active")
    list_filter = ("market", "category", "is_active")
    search_fields = ("number", "stir", "owner_name")
    autocomplete_fields = ("market", "row", "category")
