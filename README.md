# Savdo Nazorat — AI orqali bozor savdosini nazorat tizimi

Bozor do'konlarining haqiqiy savdosini kuzatib, deklaratsiya qilingan savdo bilan
solishtiradi va yashiruvchi do'konlarni signal beradi. Maqsad — soliq tushumini oshirish.

**Hozirgi holat:** sayt + inspektor/sotuvchi ilovasi (PWA) tayyor va ishlaydi.
Kamera **kamerasiz ham to'liq ishlaydi** — sotuvchi savdoni qo'lda kiritadi.
Kamera keyin qo'shiladi → qarang [`CAMERA_INTEGRATION.md`](CAMERA_INTEGRATION.md).

## Tez ishga tushirish

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # demo ma'lumot (ixtiyoriy)
python manage.py runserver
```

`http://127.0.0.1:8000/` — brauzerda oching.

### Demo loginlar (parol: `demo1234`)

| Login | Rol | Ko'radi |
|-------|-----|---------|
| `rahbar` | Rahbar | Hamma bozor, hisobot, deklaratsiya yuklash |
| `inspektor` | Inspektor | Faqat o'z bozori, tekshiruv kiritish |
| `sotuvchi` | Sotuvchi | Faqat savdo kiritish ekrani (PWA) |
| `admin` | Admin | `/admin/` to'liq boshqaruv |

## Kim nima qiladi

- **Rahbar/soliqchi** — dashboard: bozorlar, qizil/sariq signallar, do'kon tahlili,
  o'xshash do'konlar solishtiruvi, hisobot va Excel eksport, deklaratsiya yuklash.
- **Inspektor** — signal keladi → do'konga boradi → tekshiruv natijasini (foto, akt,
  jarima) kiritadi. Bu AI aniqligini o'lchaydi.
- **Sotuvchi** — telefonда PWA orqali har savdoni bir bosishda kiritadi.

## Arxitektura

Django (backend + sayt) · DRF (kamera API) · HTMX (jonli forma) · PWA (ilova) ·
SQLite (MVP) → PostgreSQL (production). Applar: `accounts markets cameras events
analytics inspections reports audit dashboard`.

Kunlik hisob-kitob:
```bash
python manage.py recompute            # statistika + signal (bugun)
python manage.py recompute --date 2026-09-01
```
Production'da buni cron/Celery beat har kecha chaqiradi.

## Ishlab chiqarishga o'tkazish

`.env` faylida (namuna: `.env.example`): `DEBUG=False`, `SECRET_KEY`,
`DB_ENGINE=postgres`, `ALLOWED_HOSTS`, `TELEGRAM_BOT_TOKEN`. So'ng
`collectstatic` + gunicorn + nginx.
