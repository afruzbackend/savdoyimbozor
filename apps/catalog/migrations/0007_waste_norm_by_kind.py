"""Chirish/buzilish me'yori mahsulot turiga qarab (hamma toifada bir xil 5% edi).

Faqat standart 5% da qolganlari o'zgaradi — admin qo'lda qo'ygan qiymatga tegilmaydi.
Qoidalar muzlatilgan (variants.default_waste keyin o'zgarsa ham natija o'zgarmaydi).
"""

from decimal import Decimal

from django.db import migrations

BY_KIND = {"clothing": "0.5", "shoes": "0.5", "kids": "0.5", "headwear": "0.5", "socks": "0.5",
           "pack_weight": "0.5", "pack_volume": "0.5", "type": "1"}
BY_SHOP = [("gul", 10), ("meva", 5), ("sabzavot", 5), ("go'sht", 2), ("baliq", 2),
           ("non", 3), ("shirinlik", 3), ("sut", 3), ("oziq", 1)]


def fill(apps, schema_editor):
    ProductCategory = apps.get_model("catalog", "ProductCategory")
    for c in ProductCategory.objects.select_related("shop_category").filter(waste_norm_percent=5):
        if c.variant_kind in BY_KIND:
            norm = Decimal(BY_KIND[c.variant_kind])
        else:
            sc = (c.shop_category.name if c.shop_category_id else "").lower()
            norm = Decimal(next((w for k, w in BY_SHOP if k in sc), 5))
        if norm != 5:
            c.waste_norm_percent = norm
            c.save(update_fields=["waste_norm_percent"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0006_fill_variant_kind")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
