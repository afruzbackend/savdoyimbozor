"""Eski telefon raqamlari "+998901234567" ko'rinishida saqlangan, yangilari "+998 90 123 45 67" —
ro'yxatlarda aralash ko'rinmasin. Faqat to'g'ri O'zbekiston raqami qayta yoziladi; qolgani tegilmaydi.
Mantiq nusxasi shu yerda (migratsiya keyin o'zgaradigan ilova kodiga bog'lanmasin)."""

from django.db import migrations


def _fmt(raw):
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 10 and digits.startswith("8"):
        digits = "998" + digits[1:]
    if len(digits) == 12 and digits.startswith("998"):
        return f"+{digits[:3]} {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    return None


def forwards(apps, schema_editor):
    for app, model, field in (
        ("accounts", "User", "phone"),
        ("shops", "Shop", "owner_phone"),
        ("sales", "Debt", "customer_phone"),
    ):
        Model = apps.get_model(app, model)
        for pk, val in Model.objects.exclude(**{field: ""}).values_list("pk", field).iterator():
            new = _fmt(val)
            if new and new != val:
                Model.objects.filter(pk=pk).update(**{field: new})


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_remove_systemsettings_fine_penalty_percent_and_more"),
        ("accounts", "0007_clear_own_visible_passwords"),
        ("shops", "0004_shop_fiscal_id"),
        ("sales", "0011_debt_sms_remind"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
