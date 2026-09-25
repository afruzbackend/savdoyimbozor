"""Zaxira nusxa: fayllar, SHA-256, aylanish, tashqi yuborish xatosi jurnalga."""

import gzip
from unittest import mock

import pytest
from django.core.management import call_command

from apps.core.models import BackupLog


def _fake_dump(target):
    with gzip.open(target, "wb") as f:
        f.write(b"-- PostgreSQL database dump\nCREATE TABLE x();\n")


@pytest.mark.django_db
def test_backup_creates_files_and_log(settings, tmp_path):
    settings.BACKUP_DIR = str(tmp_path / "bk")
    settings.BACKUP_UPLOAD_CMD = ""
    with mock.patch("apps.core.management.commands.backup.dump_database", _fake_dump):
        call_command("backup")
    log = BackupLog.objects.get()
    assert log.ok and not log.offsite_ok  # tashqi joy sozlanmagan — ogohlantirish
    assert "BACKUP_UPLOAD_CMD" in log.message
    names = {f["name"] for f in log.files}
    assert any(n.startswith("bozor-db-") for n in names)
    assert all(len(f["sha256"]) == 64 for f in log.files)


@pytest.mark.django_db
def test_backup_failure_logged_not_silent(settings, tmp_path):
    settings.BACKUP_DIR = str(tmp_path / "bk")

    def boom(target):
        raise RuntimeError("pg_dump topilmadi")

    with mock.patch("apps.core.management.commands.backup.dump_database", boom):
        call_command("backup")
    log = BackupLog.objects.get()
    assert log.ok is False and "pg_dump topilmadi" in log.message


@pytest.mark.django_db
def test_backup_rotation_keeps_last_n(settings, tmp_path):
    bk = tmp_path / "bk"
    bk.mkdir()
    for i in range(5):
        (bk / f"bozor-db-2026010{i}-0000.sql.gz").write_bytes(b"x")
    settings.BACKUP_DIR = str(bk)
    settings.BACKUP_KEEP = 2
    with mock.patch("apps.core.management.commands.backup.dump_database", _fake_dump):
        call_command("backup", "--no-media")
    assert len(list(bk.glob("bozor-db-*.sql.gz"))) == 2


@pytest.mark.django_db
def test_panel_shows_backup_status(aclient):
    r = aclient.get("/", HTTP_HOST="panel.localhost")
    assert r.status_code == 200 and r.context["backup_stale"] is True
