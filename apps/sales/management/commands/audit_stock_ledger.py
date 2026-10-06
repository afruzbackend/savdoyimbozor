"""Jurnalsiz qoldiqlarni topish; bu buyruq ma'lumotni o'zgartirmaydi."""

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from apps.catalog.models import Product
from apps.sales.models import StockMove


class Command(BaseCommand):
    help = "StockMove yozuvi yo'q mahsulotlarni hisobot qiladi (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--shop", type=int, help="Faqat shu do'kon IDsi")
        parser.add_argument("--all", action="store_true", help="Nol qoldiqli mahsulotlarni ham ko'rsatish")

    def handle(self, *args, **options):
        products = Product.objects.annotate(
            has_move=Exists(StockMove.objects.filter(product_id=OuterRef("pk")))
        ).filter(has_move=False)
        if options["shop"]:
            products = products.filter(shop_id=options["shop"])
        if not options["all"]:
            products = products.exclude(stock=0)

        missing = list(products.select_related("shop").order_by("shop_id", "pk"))
        if not missing:
            self.stdout.write(self.style.SUCCESS("Jurnalsiz qoldiq topilmadi."))
            return
        self.stdout.write(self.style.WARNING(
            f"{len(missing)} mahsulotda StockMove tarixi yo'q. Hech narsa o'zgartirilmadi."
        ))
        for product in missing:
            self.stdout.write(
                f"shop={product.shop_id} product={product.pk} stock={product.stock:g} name={product.name}"
            )
        self.stdout.write(
            "Avval manba dalillarini tekshiring, so'ng har mahsulot uchun admin'dagi "
            "qoldiq tuzatishidan foydalaning."
        )
