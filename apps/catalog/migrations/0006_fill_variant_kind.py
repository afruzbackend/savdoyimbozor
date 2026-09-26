"""Mavjud toifalarga variant turini berish (nomidan taxmin; admin panelda o'zgartiradi).

Qoidalar shu yerda muzlatilgan — keyin variants.py o'zgarsa ham migratsiya natijasi o'zgarmaydi.
"""

import re

from django.db import migrations

GUESS = [
    ("kids", r"bolalar|chaqaloq"),
    ("shoes", r"poyabzal|krossovka|tufli|etik|botinka|shippak|sandal|oyoq kiyim"),
    ("socks", r"paypoq|kolgotka"),
    ("headwear", r"bosh kiyim|do'ppi|kepka|shapka|qalpoq"),
    ("clothing", r"kurtka|ko'ylak|koylak|futbolka|shim|jinsi|palto|kostyum|libos|sviter|xalat|"
                 r"yubka|mayka|kofta|pijama|kiyim"),
    ("pack_weight", r"choy|qahva|kofe|kir yuvish|kukun|ziravor|sovun"),
    ("pack_volume", r"yog'|shampun|idish yuvish|sharbat|ichimlik|\batir\b|parfyum|suv\b"),
    ("type", r"batareyka|kabel|zaryad|lampochka|quloqchin|telefon|chiroq"),
    ("color", r"gul|atirgul|lola|mato|ip\b"),
]
OPTIONS = {
    "choy": "100 g, 250 g, 500 g, 1 kg",
    "yog'": "0,5 L, 1 L, 3 L, 5 L",
    "shampun": "250 ml, 400 ml, 1 L",
    "idish yuvish": "500 ml, 1 L, 5 L",
    "kir yuvish kukuni": "400 g, 1 kg, 3 kg, 9 kg",
    "sovun": "90 g, 150 g, 200 g",
    "batareyka": "AA, AAA, C, D, 9V",
    "usb kabel": "Type-C, Lightning, Micro-USB",
    "zaryadlagich": "Type-C, USB, Simsiz",
    "lampochka": "5 W, 9 W, 12 W, 15 W",
    "quloqchin": "Simli, Simsiz",
}


def fill(apps, schema_editor):
    ProductCategory = apps.get_model("catalog", "ProductCategory")
    for c in ProductCategory.objects.select_related("shop_category"):
        n = c.name.lower().replace("ʻ", "'").replace("’", "'")
        shop_cat = (c.shop_category.name if c.shop_category_id else "").lower()
        kind = next((k for k, rx in GUESS if re.search(rx, n)), None)
        if kind is None and "kiyim" in shop_cat:
            kind = "clothing"
        elif kind is None and "gul" in shop_cat:
            kind = "color"
        c.variant_kind = kind or "none"
        c.variant_options = OPTIONS.get(n, "")
        c.save(update_fields=["variant_kind", "variant_options"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_category_variant_kind")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
