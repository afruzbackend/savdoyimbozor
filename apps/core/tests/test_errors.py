"""Custom xato sahifalari (404/403/500) prod (DEBUG=False) rejimida ishlashi."""

import pytest
from django.template.loader import get_template
from django.test import Client, override_settings


@pytest.mark.django_db
@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
def test_custom_404():
    r = Client().get("/bunday-sahifa-umuman-yoq/", HTTP_HOST="testserver")
    assert r.status_code == 404
    assert "Sahifa topilmadi" in r.content.decode()


def test_error_templates_exist():
    for t in ("404.html", "403.html", "500.html"):
        assert get_template(t) is not None
