"""Zaxira nusxa: PostgreSQL + fotolar (media) → siqilgan fayllar, SHA-256, aylanish, tashqariga.

    python manage.py backup                 # baza + media
    python manage.py backup --no-media      # faqat baza

Muhim: server bozor ichida bo'lsa, yong'in ma'lumotni ham yo'q qiladi. Shuning uchun
BACKUP_UPLOAD_CMD (masalan `rclone copy {path} offsite:bozor-backup`) sozlanishi SHART —
aks holda jurnalda "tashqariga yuborilmadi" deb ogohlantiriladi.
Kechasi Celery beat (02:30) yoki Windows Task Scheduler / cron orqali ishga tushiriladi.

Tiklash (qo'lda):  gunzip -c bozor-db-YYYYMMDD-HHMM.sql.gz | psql -d bozor
                   tar -xzf bozor-media-YYYYMMDD-HHMM.tar.gz -C <MEDIA_ROOT ning otasi>
"""

from __future__ import annotations

import gzip
import hashlib
import os
import shlex
import subprocess
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_database(target: Path) -> None:
    """pg_dump chiqishini oqim bilan gzip'ga yozadi (xotira to'lmaydi)."""
    db = settings.DATABASES["default"]
    env = dict(os.environ)
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = str(db["PASSWORD"])
    cmd = [settings.PG_DUMP_BIN, "--no-owner", "--no-privileges", "-h", str(db.get("HOST") or
           "127.0.0.1"), "-p", str(db.get("PORT") or 5432), "-U", str(db.get("USER") or ""),
           str(db["NAME"])]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    with gzip.open(target, "wb", compresslevel=6) as out:
        for chunk in iter(lambda: proc.stdout.read(1 << 20), b""):
            out.write(chunk)
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump xatosi: {err.strip()[:300]}")


def archive_media(target: Path) -> None:
    root = Path(settings.MEDIA_ROOT)
    with tarfile.open(target, "w:gz") as tar:
        if root.exists():
            tar.add(root, arcname=root.name)


def verify_gzip(path: Path) -> None:
    """Fayl butunligini tekshiradi (oxirigacha o'qib) — buzuq zaxira jim qolmasin."""
    with gzip.open(path, "rb") as f:
        while f.read(1 << 20):
            pass


class Command(BaseCommand):
    help = "Baza va fotolarning zaxira nusxasini oladi (SHA-256, aylanish, tashqariga yuborish)."

    def add_arguments(self, parser):
        parser.add_argument("--no-media", action="store_true")

    def handle(self, *args, **opts):
        from apps.core.models import BackupLog

        out_dir = Path(settings.BACKUP_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        files, messages = [], []
        ok = offsite_ok = False
        try:
            db_file = out_dir / f"bozor-db-{stamp}.sql.gz"
            dump_database(db_file)
            verify_gzip(db_file)
            targets = [db_file]
            if not opts["no_media"]:
                media_file = out_dir / f"bozor-media-{stamp}.tar.gz"
                archive_media(media_file)
                verify_gzip(media_file)
                targets.append(media_file)
            for t in targets:
                digest = _sha256(t)
                (t.parent / (t.name + ".sha256")).write_text(f"{digest}  {t.name}\n")
                files.append({"name": t.name, "size": t.stat().st_size, "sha256": digest})
            ok = True
            offsite_ok, msg = self._upload(targets)
            messages.append(msg)
            messages.append(self._rotate(out_dir))
        except Exception as e:  # noqa: BLE001 — xato jurnalga yozilsin, jim o'tmasin
            messages.append(f"XATO: {e}")
        log = BackupLog.objects.create(
            ok=ok, offsite_ok=offsite_ok, files=files,
            total_bytes=sum(f["size"] for f in files), message="\n".join(m for m in messages if m),
        )
        style = self.style.SUCCESS if ok else self.style.ERROR
        status = "OK" if ok else "XATO"
        offsite = "ha" if offsite_ok else "yo'q"
        self.stdout.write(style(f"Zaxira: {status} · {len(files)} fayl · "
                                f"{log.total_bytes / 1e6:.1f} MB · tashqariga: {offsite}"))
        for m in messages:
            if m:
                self.stdout.write(f"  {m}")
        return None

    def _upload(self, targets):
        cmd_tpl = settings.BACKUP_UPLOAD_CMD
        if not cmd_tpl:
            return False, ("OGOHLANTIRISH: BACKUP_UPLOAD_CMD sozlanmagan — zaxira faqat shu "
                           "serverda. Yong'in/avariyada yo'qoladi.")
        for t in targets:
            for path in (t, t.parent / (t.name + ".sha256")):
                # Windows (cmd.exe) va Linux (sh) qo'shtirnoq qoidalari har xil
                quoted = (subprocess.list2cmdline([str(path)]) if os.name == "nt"
                          else shlex.quote(str(path)))
                cmd = cmd_tpl.replace("{path}", quoted)
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3600)
                if r.returncode != 0:
                    return False, f"Tashqariga yuborish xatosi: {(r.stderr or r.stdout)[:300]}"
        return True, "Tashqi joyga yuborildi."

    def _rotate(self, out_dir: Path) -> str:
        keep = max(1, settings.BACKUP_KEEP)
        removed = 0
        for prefix in ("bozor-db-", "bozor-media-"):
            items = sorted(p for p in out_dir.glob(prefix + "*.gz"))
            for old in items[:-keep]:
                old.unlink(missing_ok=True)
                (old.parent / (old.name + ".sha256")).unlink(missing_ok=True)
                removed += 1
        return f"Eski nusxalar o'chirildi: {removed}" if removed else ""
