"""Bosh admin (panel): do'kon+sotuvchi yaratish, rol chegarasi."""

import pytest
from django.test import Client

from apps.accounts.services import create_inspector
from apps.shops.models import Shop
from conftest import PW

PANEL_HOST = "panel.localhost"


@pytest.mark.django_db
def test_admin_creates_shop_with_location(aclient, market):
    from apps.catalog.models import ShopCategory

    cat = ShopCategory.objects.create(name="Meva-sabzavot")
    r = aclient.post(
        "/hisob/yangi/",
        {
            "role": "seller", "full_name": "Yangi Sotuvchi", "phone": "+998901112233",
            "number": "77", "stir": "555555555", "market": market.pk, "category": cat.pk,
            "address": "Chorsu 3-qator",
        },
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302
    s = Shop.objects.get(number="77")
    assert s.stir == "555555555"
    assert s.category == cat  # savdo turi
    # Koordinata so'ralmaydi — bozor markazi olinadi
    assert s.latitude == market.latitude
    assert s.staff.exists()  # sotuvchi ochildi


@pytest.mark.django_db
def test_admin_page_renders(aclient):
    for p in ["/", "/foydalanuvchilar/", "/hisob/yangi/"]:
        assert aclient.get(p, HTTP_HOST=PANEL_HOST).status_code == 200


@pytest.mark.django_db
def test_inspector_cannot_open_panel(market):
    """Tekshiruvchi panel sahifalariga kira olmaydi — urlconf'ida yo'q (404).

    Bosh sahifasida o'z (nazorat) dashboardini ko'radi.
    """
    cred = create_inspector("Nodir", [market])
    u = cred["user"]
    u.set_password(PW)
    u.must_change_password = False
    u.save()
    c = Client()
    c.force_login(u)
    assert c.get("/").status_code == 200  # o'z dashboardi
    assert c.get("/foydalanuvchilar/").status_code == 404  # panel sahifasi — yo'q
    assert c.get("/hisob/yangi/").status_code == 404


@pytest.mark.django_db
def test_seller_blocked_from_panel(sclient):
    """Sotuvchi panel sahifalariga kira olmaydi (404), bosh sahifasida o'z sahifasi."""
    assert sclient.get("/").status_code == 200
    assert sclient.get("/foydalanuvchilar/").status_code == 404


@pytest.mark.django_db
def test_admin_cannot_block_self(aclient, admin_user):
    """Admin o'zini bloklay olmaydi (aks holda tizimga kira olmay qoladi)."""
    r = aclient.post(
        f"/foydalanuvchilar/{admin_user.pk}/holat/", HTTP_HOST=PANEL_HOST
    )
    assert r.status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.is_active is True


@pytest.mark.django_db
def test_cannot_block_last_superadmin(aclient, admin_user):
    """Oxirgi faol super adminni (o'zidan boshqa admin yo'q) bloklab bo'lmaydi."""
    from apps.accounts.models import Role, User

    other = User.objects.create(
        username="admin2", role=Role.SUPERADMIN, is_staff=True, is_superuser=True
    )
    other.set_password(PW)
    other.must_change_password = False
    other.save()
    # admin_user admin2'ni bloklaydi -> qoladi 1 ta faol admin (admin_user) -> ruxsat
    r = aclient.post(f"/foydalanuvchilar/{other.pk}/holat/", HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302
    other.refresh_from_db()
    assert other.is_active is False
    # endi admin2 (bloklangan) qayta faollashsin, keyin admin_user'ni bloklashga urinib ko'ramiz:
    # faqat 1 ta faol admin qolgani uchun (admin2 bloklangan) admin_user'ni bloklab bo'lmaydi
    c2 = Client()
    other.is_active = True
    other.save()
    c2.force_login(other)
    # admin2 admin_user'ni bloklaydi (2 ta faol admin bor) -> ruxsat, qoladi admin2
    r = c2.post(f"/foydalanuvchilar/{admin_user.pk}/holat/", HTTP_HOST=PANEL_HOST)
    admin_user.refresh_from_db()
    assert admin_user.is_active is False
    # endi faqat admin2 faol -> admin2 o'zini bloklay olmaydi (self guard)
    r = c2.post(f"/foydalanuvchilar/{other.pk}/holat/", HTTP_HOST=PANEL_HOST)
    other.refresh_from_db()
    assert other.is_active is True


@pytest.mark.django_db
def test_new_shop_increases_market_count(aclient, market):
    """Yangi do'kon (mode=new) ochilganda bozordagi do'kon soni ko'payadi —
    yashirin 'shop' select qiymati e'tiborga olinmasligi kerak."""
    from apps.catalog.models import ShopCategory

    cat = ShopCategory.objects.create(name="Kiyim")
    before = market.shops.count()
    r = aclient.post(
        "/hisob/yangi/",
        {
            "role": "seller", "mode": "new", "full_name": "Yangi Do'kon Egasi",
            "phone": "+998900000000", "number": "", "stir": "999888777",
            "market": market.pk, "category": cat.pk, "address": "1-qator",
        },
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302
    assert market.shops.count() == before + 1


@pytest.mark.django_db
def test_new_shop_ignores_stray_shop_value(aclient, market, shop):
    """mode=new bo'lsa, POST'dagi 'shop' qiymati (yashirin select) e'tiborsiz —
    mavjud do'konga biriktirmasdan yangi do'kon yaratadi."""
    from apps.catalog.models import ShopCategory

    cat = ShopCategory.objects.create(name="Kiyim")
    before = market.shops.count()
    r = aclient.post(
        "/hisob/yangi/",
        {
            "role": "seller", "mode": "new", "shop": shop.pk,  # <- yashirin, e'tiborsiz
            "full_name": "Boshqa Egasi", "phone": "+998900000001",
            "number": "", "stir": "111222333", "market": market.pk, "category": cat.pk,
        },
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302
    assert market.shops.count() == before + 1  # yangi do'kon yaratildi


@pytest.mark.django_db
def test_new_shop_requires_category(aclient, market):
    """Savdo turi tanlanmasa yangi do'kon yaratilmaydi."""
    before = market.shops.count()
    r = aclient.post(
        "/hisob/yangi/",
        {
            "role": "seller", "mode": "new", "full_name": "Egasi",
            "number": "", "stir": "444555666", "market": market.pk, "category": "",
        },
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302  # xato bilan qaytariladi
    assert market.shops.count() == before  # yaratilmadi


@pytest.mark.django_db
def test_cannot_delete_category_in_use(aclient, shop):
    """Do'kon ishlatayotgan savdo turini o'chirib bo'lmaydi (jimgina null bo'lib ketmasin)."""
    from apps.catalog.models import ShopCategory

    cat = shop.category
    r = aclient.post(
        "/toifalar/", {"action": "delete", "id": cat.pk}, HTTP_HOST=PANEL_HOST
    )
    assert r.status_code == 302
    assert ShopCategory.objects.filter(pk=cat.pk).exists()  # o'chirilmadi
    shop.refresh_from_db()
    assert shop.category_id == cat.pk  # do'kon turi saqlanib qoldi


@pytest.mark.django_db
def test_can_delete_unused_category(aclient):
    """Ishlatilmayotgan savdo turini o'chirish mumkin."""
    from apps.catalog.models import ShopCategory

    cat = ShopCategory.objects.create(name="Bo'sh tur")
    r = aclient.post(
        "/toifalar/", {"action": "delete", "id": cat.pk}, HTTP_HOST=PANEL_HOST
    )
    assert r.status_code == 302
    assert not ShopCategory.objects.filter(pk=cat.pk).exists()


@pytest.mark.django_db
def test_settings_reject_lockout_and_bad_thresholds(aclient):
    """login_max_attempts=0 (hammani bloklash) va yashil<=sariq rad etiladi."""
    from apps.core.models import SystemSettings

    s = SystemSettings.get_solo()
    old_attempts, old_green = s.login_max_attempts, s.green_threshold
    aclient.post("/sozlamalar/", {"login_max_attempts": "0"}, HTTP_HOST=PANEL_HOST)
    aclient.post("/sozlamalar/", {"green_threshold": "40", "yellow_threshold": "60"},
                 HTTP_HOST=PANEL_HOST)
    aclient.post("/sozlamalar/", {"tax_rate_percent": "abc"}, HTTP_HOST=PANEL_HOST)  # crash yo'q
    SystemSettings._cache = None
    s = SystemSettings.get_solo()
    assert s.login_max_attempts == old_attempts
    assert s.green_threshold == old_green


@pytest.mark.django_db
def test_login_sheet_shown_only_once(aclient):
    session = aclient.session
    session["login_sheet"] = [{"name": "X", "login": "1", "password": "SECRET1", "shop": ""}]
    session.save()
    r1 = aclient.get("/login-varaqasi/", HTTP_HOST=PANEL_HOST)
    r2 = aclient.get("/login-varaqasi/", HTTP_HOST=PANEL_HOST)
    assert "SECRET1" in r1.content.decode()
    assert "SECRET1" not in r2.content.decode()


def test_excel_str_float_numbers():
    from apps.core.format import excel_str

    assert excel_str(25.0) == "25"
    assert excel_str(300000001.0) == "300000001"
    assert excel_str("A-12") == "A-12"
    assert excel_str(None) == ""


@pytest.mark.django_db
def test_admin_edits_shop(aclient, shop):
    from apps.catalog.models import ShopCategory

    cat = ShopCategory.objects.create(name="Kiyim-kechak")
    assert aclient.get(f"/dokon/{shop.pk}/", HTTP_HOST=PANEL_HOST).status_code == 200
    r = aclient.post(
        f"/dokon/{shop.pk}/",
        {"owner_name": "Yangi Egasi", "stir": "111 222 333", "number": shop.number,
         "category": cat.pk, "owner_phone": "+998901234567", "closed": ["6", "0", "9"],
         "is_active": "on"},
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302
    shop.refresh_from_db()
    assert shop.owner_name == "Yangi Egasi"
    assert shop.stir == "111222333"
    assert shop.category == cat
    assert shop.closed_weekdays == "0,6"  # 9 — noto'g'ri kun, tashlandi


@pytest.mark.django_db
def test_shop_edit_rejects_duplicate_number_and_blank(aclient, shop, market):
    other = Shop.objects.create(market=market, number="999", stir="1")
    base = {"owner_name": "X", "stir": "123", "category": shop.category_id}
    aclient.post(f"/dokon/{shop.pk}/", {**base, "number": "999"}, HTTP_HOST=PANEL_HOST)
    aclient.post(f"/dokon/{shop.pk}/", {**base, "number": shop.number, "owner_name": ""},
                 HTTP_HOST=PANEL_HOST)
    old = shop.number
    shop.refresh_from_db()
    assert shop.number == old and shop.owner_name != "X"
    assert other.number == "999"


@pytest.mark.django_db
def test_admin_edits_inspector_markets(aclient, market):
    from apps.geo.models import Market

    m2 = Market.objects.create(region=market.region, name="Oloy")
    cred = create_inspector("Nodir Aliyev", [market])
    u = cred["user"]
    r = aclient.post(
        f"/foydalanuvchilar/{u.pk}/",
        {"full_name": "Nodir Karimov", "phone": "+998900000009", "markets": [m2.pk]},
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302
    u.refresh_from_db()
    assert u.last_name == "Karimov"
    assert list(u.assigned_markets.all()) == [m2]


@pytest.mark.django_db
def test_inspector_without_market_not_created(aclient):
    from apps.accounts.models import Role, User

    before = User.objects.filter(role=Role.INSPECTOR).count()
    aclient.post("/hisob/yangi/", {"role": "inspector", "full_name": "Bo'sh"},
                 HTTP_HOST=PANEL_HOST)
    assert User.objects.filter(role=Role.INSPECTOR).count() == before


@pytest.mark.django_db
def test_user_search_by_name_and_shop(aclient, seller, shop):
    r = aclient.get(f"/foydalanuvchilar/?q={shop.number}", HTTP_HOST=PANEL_HOST)
    assert seller.username in r.content.decode()


@pytest.mark.django_db
def test_password_not_in_page_source_and_reveal_is_audited(aclient, shop):
    """Parol sahifa manbasida yo'q (oldin "yashirin" bo'lsa ham HTML'da edi) va inline JS'ga
    qo'yilmaydi (sotuvchi ') li parol qo'yib admin brauzerida kod ishlata olardi)."""
    from apps.accounts.services import create_seller
    from apps.core.models import AuditLog

    cred = create_seller(shop, full_name="Ali")
    u = cred["user"]
    evil = "x');alert(1)//"
    u.set_password_visible(evil)
    u.save()
    for url in ("/foydalanuvchilar/", f"/bozorlar/{shop.market_id}/"):
        html = aclient.get(url, HTTP_HOST="panel.localhost").content.decode()
        assert "alert(1)" not in html and cred["login"] in html
        assert f"/foydalanuvchilar/{u.pk}/parol/korish/" in html
    assert aclient.get(f"/foydalanuvchilar/{u.pk}/parol/korish/", HTTP_HOST="panel.localhost").status_code == 405
    r = aclient.post(f"/foydalanuvchilar/{u.pk}/parol/korish/", HTTP_HOST="panel.localhost")
    assert r.status_code == 200 and r.json() == {"password": evil}
    assert AuditLog.objects.filter(detail__contains=f"Parol ko'rildi: {u.username}").exists()
