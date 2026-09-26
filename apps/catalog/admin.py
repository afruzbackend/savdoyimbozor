from django.contrib import admin

from .models import Product, ProductCategory, ShopCategory


@admin.register(ShopCategory)
class ShopCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "shop_category", "default_unit", "variant_kind", "waste_norm_percent")
    list_filter = ("shop_category", "variant_kind")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "shop",
        "category",
        "unit",
        "buy_price",
        "sell_price",
        "stock",
        "is_active",
    )
    list_filter = ("is_active", "category")
    search_fields = ("name", "barcode")
    autocomplete_fields = ("shop", "category")
