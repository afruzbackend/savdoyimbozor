#!/bin/sh
set -e

# Baza tayyor bo'lguncha kutamiz
echo "Baza kutilmoqda..."
python - <<'PY'
import os, time, psycopg
url = os.environ.get("DATABASE_URL", "")
for i in range(30):
    try:
        psycopg.connect(url, connect_timeout=2).close()
        print("Baza tayyor.")
        break
    except Exception:
        time.sleep(1)
PY

# Faqat web konteynerida migratsiya + statik
if [ "$RUN_MIGRATIONS" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
fi

exec "$@"
