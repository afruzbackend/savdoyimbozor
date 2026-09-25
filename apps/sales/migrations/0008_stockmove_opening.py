"""Jurnal boshlanishi: har mahsulotning joriy qoldig'i "boshlang'ich qoldiq" bo'lib yoziladi."""

from django.db import migrations
from django.utils import timezone


def opening(apps, schema_editor):
    from apps.sales.models import stock_move_hash

    Product = apps.get_model("catalog", "Product")
    StockMove = apps.get_model("sales", "StockMove")
    now = timezone.now()
    last = {}
    for p in Product.objects.exclude(stock=0).order_by("shop_id", "id"):
        prev = last.get(p.shop_id, "")
        h = stock_move_hash(prev, p.shop_id, p.id, "opening", p.stock, p.stock,
                            p.sell_price, "Jurnal boshi", now)
        StockMove.objects.create(
            shop_id=p.shop_id, product_id=p.id, kind="opening", qty=p.stock, balance=p.stock,
            unit_price=p.sell_price, ref="Jurnal boshi", created_at=now, prev_hash=prev, hash=h,
        )
        last[p.shop_id] = h


class Migration(migrations.Migration):
    dependencies = [("sales", "0007_stockmove"), ("catalog", "0003_alter_product_unit_and_more")]
    operations = [migrations.RunPython(opening, migrations.RunPython.noop)]
