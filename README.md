# Bozor Nazorat — bozor savdosini shaffof nazorat qilish tizimi

Bozordagi do'konlar savdosini uch manbadan (sotuvchi kiritgan, kassa/deklaratsiya,
kamera+AI) solishtirib, har do'konga **rostlik darajasi (%)** beradi va mos kelmasa
tekshiruvchiga **signal** yuboradi. Muhim tamoyil: natija — tekshiruvga signal,
jarima uchun dalil emas; yakuniy qarorni inspektor joyida qabul qiladi.

Uch interfeys, bitta backend (host bo'yicha ajraladi):
- **sotuvchi.** — sotuvchi (telefon): tez/skaner sotuv, kirim, kun yakuni, nasiya, hisobot
- **nazorat.** — tekshiruvchi (kompyuter): dashboard, bozor xaritasi, do'kon sahifasi, signallar
- **panel.** — super admin: hisob ochish, Excel import, sozlamalar, audit

## Texnologiya
Django + DRF (API-first) · PostgreSQL · Celery + Redis · HTMX + Alpine.js · Chart.js ·
custom dizayn tizimi (light/dark). Barcha aktivlar **lokal** (shrift/ikonka/JS — CDN yo'q),
demo internetsiz ishlaydi.

## Ishga tushirish — Docker (tavsiya)
```bash
cp .env.example .env          # SECRET_KEY, DB_PASSWORD ni to'ldiring
docker compose up --build     # web, db, redis, celery, beat, nginx
docker compose exec web python manage.py seed_demo --reset
docker compose exec web python manage.py simulate_camera   # ixtiyoriy (jonli demo)
```
So'ng brauzerda: `http://nazorat.localhost/`, `http://sotuvchi.localhost/`, `http://panel.localhost/`
(nginx 80-portda; Chrome `*.localhost`ni 127.0.0.1'ga yechadi).

## Ishga tushirish — lokal (Docker'siz)
Lokal PostgreSQL kerak (18 ham bo'ladi). Baza va rol oching:
```bash
psql -U postgres -c "CREATE ROLE bozor LOGIN PASSWORD 'bozor';" -c "CREATE DATABASE bozor OWNER bozor;"
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo --reset
python manage.py runserver
```
`http://nazorat.localhost:8000/` · `http://sotuvchi.localhost:8000/` · `http://panel.localhost:8000/`

## Demo loginlar (parol: `demo1234`)
| Login | Rol | Interfeys |
|-------|-----|-----------|
| `nazorat` | Tekshiruvchi | nazorat.localhost |
| `sotuvchi` | Sotuvchi | sotuvchi.localhost |
| `admin` | Super admin | panel.localhost |

## Demo ssenariysi
1. **nazorat** bilan kiring → dashboard va **bozor xaritasi**: yashiruvchi do'konlar qizil
   (kassa yashiradi yoki narx past). Do'kon sahifasida rostlik tarkibi va grafik.
2. **sotuvchi** bilan kiring (telefon rejimida) → tez sotuv (klaviatura + chegirma) va
   skaner sotuv; hisobotда rostlik va "qanday oshiraman" maslahati.
3. **admin** bilan kiring → hisob ochish → chop etiladigan login varaqasi; sozlamalar; audit.

## Telefonda sinash
Sotuvchi interfeysi telefon uchun. Bir tarmoqda kompyuter IP'sini oching
(`http://<IP>:8000/`) yoki nginx bilan `sotuvchi.<domen>`. Internet uzilsa sotuv
telefonda saqlanib, tiklanganda avtomatik yuboriladi (offline navbat).

## Kunlik hisob-kitob
```bash
python manage.py recompute            # bugungi rostlik + signal
python manage.py recompute --date 2026-09-01
```
Production'da Celery beat buni har 5 daqiqa / har kecha avtomatik bajaradi.

## Kamera keyin qo'shiladi
Backend kontrakti tayyor (`/api/cameras/config/`, `/api/events/`, heartbeat).
Batafsil: [`CLAUDE.md`](CLAUDE.md) va [`ai_worker/worker.py`](ai_worker/worker.py).

To'liq talablar: [`docs/SPEC.md`](docs/SPEC.md).
