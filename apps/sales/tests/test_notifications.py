"""Bildirishnoma va nasiya eslatmasi, nol-savdo majburiy izohi."""

import pytest
from django.utils import timezone

from apps.core.models import Notification
from apps.sales.models import Debt
from conftest import SELLER_HOST


@pytest.mark.django_db
def test_due_debt_creates_notification(sclient, shop):
    Debt.objects.create(
        shop=shop, customer_name="Ali", amount=50000, due_date=timezone.localdate()
    )
    sclient.get("/bildirishnomalar/", HTTP_HOST=SELLER_HOST)
    assert Notification.objects.filter(kind=Notification.Kind.DEBT_DUE).exists()


@pytest.mark.django_db
def test_due_debt_notification_not_duplicated(sclient, shop):
    Debt.objects.create(
        shop=shop, customer_name="Ali", amount=50000, due_date=timezone.localdate()
    )
    sclient.get("/bildirishnomalar/", HTTP_HOST=SELLER_HOST)
    sclient.get("/bildirishnomalar/", HTTP_HOST=SELLER_HOST)  # ikkinchi marta
    assert Notification.objects.filter(kind=Notification.Kind.DEBT_DUE).count() == 1


@pytest.mark.django_db
def test_notification_open_marks_read(sclient, seller):
    n = Notification.objects.create(
        user=seller, kind=Notification.Kind.INFO, title="Test", url="/nasiya/"
    )
    r = sclient.get(f"/bildirishnomalar/{n.pk}/", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 302
    n.refresh_from_db()
    assert n.is_read is True


@pytest.mark.django_db
def test_zero_sales_forces_appeal(sclient, shop):
    """Tushuntirilmagan 'savdo yo'q' signali bo'lsa — home e'tirozga yo'naltiradi."""
    from datetime import timedelta

    from apps.analytics.models import Alert

    # Tugagan (kechagi) kun — bugungi kun uchun tushuntirish talab qilinmaydi
    Alert.objects.create(
        shop=shop, date=timezone.localdate() - timedelta(days=1), kind=Alert.Kind.ZERO_SALES,
        level="red", reason="test",
    )
    r = sclient.get("/", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 302
    assert "/e-tiroz/" in r.url


@pytest.mark.django_db
def test_zero_sales_explained_unblocks_home(sclient, shop):
    from datetime import timedelta

    from apps.analytics.models import Alert

    al = Alert.objects.create(
        shop=shop, date=timezone.localdate() - timedelta(days=1), kind=Alert.Kind.ZERO_SALES,
        level="red", reason="test",
    )
    sclient.post(
        "/e-tiroz/", {"nosales_alert": al.pk, "message": "bozor yopiq edi"}, HTTP_HOST=SELLER_HOST
    )
    al.refresh_from_db()
    # Sotuvchi signalni O'ZI yopa olmaydi — qarorni nazoratchi qabul qiladi
    assert al.status == Alert.Status.NEW
    assert al.appeals.count() == 1
    assert sclient.get("/", HTTP_HOST=SELLER_HOST).status_code == 200
