"""Umumiy pytest fikstura'lari — integratsion testlar uchun minimal domen."""

import pytest
from django.test import Client

from apps.accounts.services import create_inspector, create_seller
from apps.catalog.models import Product, ProductCategory, ShopCategory
from apps.geo.models import Market, Region, Row
from apps.shops.models import Shop

PW = "TestParol9"


@pytest.fixture
def market(db):
    region = Region.objects.create(name="Toshkent")
    return Market.objects.create(region=region, name="Chorsu", latitude=41.32, longitude=69.23)


@pytest.fixture
def shop(market):
    row = Row.objects.create(market=market, label="A")
    cat = ShopCategory.objects.create(name="Oziq-ovqat")
    return Shop.objects.create(
        market=market, row=row, category=cat, number="1", stir="123456789",
        owner_name="Ali Valiyev", latitude=41.32, longitude=69.23,
    )


@pytest.fixture
def seller(shop):
    """Do'kon egasi — parol PW ga o'rnatiladi, blok/parol-almashtirish o'chiriladi."""
    cred = create_seller(shop, full_name="Ali Valiyev")
    user = cred["user"]
    user.set_password(PW)
    user.must_change_password = False
    user.save()
    return user


@pytest.fixture
def inspector(market):
    cred = create_inspector("Nodir Inspektor", [market])
    user = cred["user"]
    user.set_password(PW)
    user.must_change_password = False
    user.save()
    return user


@pytest.fixture
def product(shop):
    cat = ProductCategory.objects.create(name="Pomidor")
    return Product.objects.create(
        shop=shop, name="Pomidor", category=cat, barcode="2000001",
        buy_price=8000, sell_price=12000, stock=100,
    )


@pytest.fixture
def sclient(seller):
    c = Client()
    c.force_login(seller)
    return c


@pytest.fixture
def iclient(inspector):
    c = Client()
    c.force_login(inspector)
    return c


@pytest.fixture
def admin_user(db):
    from apps.accounts.models import Role, User

    u = User.objects.create(
        username="admin1", role=Role.SUPERADMIN, is_staff=True, is_superuser=True
    )
    u.set_password(PW)
    u.must_change_password = False
    u.save()
    return u


@pytest.fixture
def aclient(admin_user):
    c = Client()
    c.force_login(admin_user)
    return c


SELLER_HOST = "sotuvchi.localhost"
INSPECTOR_HOST = "nazorat.localhost"


def photo_file(name="rasta.jpg"):
    """Haqiqiy (Pillow) rasm — foto tekshiruvidan o'tadi (kun yakuni, kirim, chiqarish)."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 3), (120, 90, 30)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture(autouse=True)
def _media_tmp(settings, tmp_path):
    """Testlarda yuklangan fotolar haqiqiy media/ papkasini ifloslamasin."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
