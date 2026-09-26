"""Egasi o'zi tanlagan parollarning ochiq nusxasini o'chirish.

Oldin foydalanuvchi parolini almashtirganda yangi parol ham ochiq matnda saqlanardi. Endi faqat
admin bergan vaqtinchalik parol (must_change_password=True — egasi hali almashtirmagan) qoladi.
Qaytarib bo'lmaydi (va kerak ham emas): parol xeshi o'zgarmaydi, hamma avvalgidek kiradi.
"""

from django.db import migrations


def clear(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(must_change_password=False).exclude(visible_password="").update(visible_password="")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_user_backup_codes_user_totp_enabled_and_more")]
    operations = [migrations.RunPython(clear, migrations.RunPython.noop)]
