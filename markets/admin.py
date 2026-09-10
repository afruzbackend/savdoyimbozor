from django.contrib import admin

from .models import Market, ProductCategory, Shop


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "is_active", "shop_count")
    search_fields = ("name", "region", "address")
    list_filter = ("is_active", "region")

    @admin.display(description="Do'konlar soni")
    def shop_count(self, obj):
        return obj.shops.count()


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "avg_ticket", "waste_norm_percent")


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "market", "category", "stir", "owner_name", "is_active")
    list_filter = ("market", "category", "is_active")
    search_fields = ("name", "stir", "owner_name")
    autocomplete_fields = ("market",)
