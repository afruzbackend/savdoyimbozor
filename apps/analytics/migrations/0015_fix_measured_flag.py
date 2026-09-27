"""Eski "o'lchangan" belgilarini yangi qoidaga keltirish.

Ilgari faqat narx qismi bor kun ham `measured=True` yozilardi (1 000 so'm yozgan do'kon ham
"100% yashil"). Endi o'lchangan = savdo hajmini tekshiruvchi manba bor (kassa/kamera/qoldiq).
Eski qatorlar tuzatilmasa xarita/dashboard ularni hisobga olib, rostlik noto'g'ri ko'rinardi.
"""

from django.db import migrations

VOLUME_PARTS = ("cash", "camera", "stock")


def forwards(apps, schema_editor):
    DailyScore = apps.get_model("analytics", "DailyScore")
    stale = []
    for pk, parts in (
        DailyScore.objects.filter(measured=True)
        .exclude(parts={})
        .values_list("pk", "parts")
        .iterator(chunk_size=2000)
    ):
        if parts and not any(parts.get(k) is not None for k in VOLUME_PARTS):
            stale.append(pk)
    for i in range(0, len(stale), 1000):
        DailyScore.objects.filter(pk__in=stale[i : i + 1000]).update(measured=False)


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0014_inspection_fine_level"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
