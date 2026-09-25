"""Eski mantiq kun TUGAMASDAN yaratgan soxta signallarni yopadi.

Ilgari har sotuvdan keyin bugungi kun uchun signal yaratilardi: ertalab hali sotmagan
do'konga "savdo yo'q", kunlik o'rtachaga yetmagan savdoga "keskin tushdi" chiqardi.
Endi signal faqat tugagan kun uchun. Bu migratsiya o'tmishdagi shunday signallarni
yakuniy ma'lumot bo'yicha qayta tekshiradi va asossizlarini "e'tiborsiz" qiladi.
"""

from django.db import migrations


def cleanup(apps, schema_editor):
    Alert = apps.get_model("analytics", "Alert")
    DailyScore = apps.get_model("analytics", "DailyScore")
    Sale = apps.get_model("sales", "Sale")
    SystemSettings = apps.get_model("core", "SystemSettings")

    cfg = SystemSettings.objects.filter(pk=1).first()
    drop_pct = getattr(cfg, "anomaly_drop_pct", 60) or 60

    # 1) "Savdo yo'q" — lekin o'sha kuni savdo BOR edi
    for a in Alert.objects.filter(kind="zero_sales", status__in=("new", "assigned")):
        if Sale.objects.filter(shop_id=a.shop_id, created_at__date=a.date).exists():
            a.status = "dismissed"
            a.save(update_fields=["status"])

    # 2) "Keskin tushdi" — yakuniy kunlik savdo chegaradan tushmagan
    for a in Alert.objects.filter(kind="anomaly", status__in=("new", "assigned")):
        final = sum(
            s.total for s in Sale.objects.filter(shop_id=a.shop_id, created_at__date=a.date)
        )
        prior = list(
            DailyScore.objects.filter(
                shop_id=a.shop_id, date__lt=a.date, entered_sales__gt=0
            ).order_by("-date").values_list("entered_sales", flat=True)[:30]
        )
        if len(prior) < 5:
            continue
        avg = sum(prior) / len(prior)
        if avg > 0 and round((1 - final / avg) * 100) < drop_pct:
            a.status = "dismissed"
            a.save(update_fields=["status"])


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0006_dailyscore_measured"),
        ("sales", "0006_debt_paid_amount_debt_sale_and_more"),
        ("core", "0006_systemsettings_fine_penalty_percent"),
    ]

    operations = [migrations.RunPython(cleanup, migrations.RunPython.noop)]
