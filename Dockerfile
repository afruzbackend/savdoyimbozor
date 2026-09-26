FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# Tizim kutubxonalari (Pillow/psycopg) + pg_dump 16 (zaxira nusxa).
# Debian'dagi postgresql-client 15 — postgres:16 serverini dump qila olmaydi, shuning uchun PGDG.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSo /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update && apt-get install -y --no-install-recommends libpq5 postgresql-client-16 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Root EMAS: alohida cheklangan foydalanuvchi. Yoziladigan joylar faqat statik/media/zaxira/inbox
# (nomli volume birinchi yaratilganda egalik shu kataloglardan olinadi).
RUN chmod +x docker/entrypoint.sh \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && mkdir -p /app/staticfiles /app/media /backups /tax_inbox \
 && chown -R app:app /app/staticfiles /app/media /backups /tax_inbox
USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
