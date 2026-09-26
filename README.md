# Bozor Nazorat — bozor savdosini shaffof nazorat qilish tizimi

Bozordagi do'konlar savdosini bir necha manbadan (sotuvchi kiritgan savdo,
kassa/deklaratsiya va — keyinchalik — kamera+AI) solishtirib, har do'konga
**rostlik darajasi (%)** beradi va mos kelmasa tekshiruvchiga **signal** yuboradi.

> **Muhim tamoyil:** natija — tekshiruvga **signal**, jarima uchun avtomatik dalil
> **emas**. Barcha pul raqamlari "taxminiy"; yakuniy qarorni inspektor joyida qabul qiladi.

## Bitta manzil, uch rol
Hammasi **bitta host**da (masalan `localhost:8000`). Kim kirsa — roliga qarab o'z
interfeysini ko'radi. Ro'yxatdan o'tish yo'q: **loginni admin beradi**.
- **Sotuvchi** — telefon: tez/skaner sotuv, kirim, qaytarish, kun yakuni, kassa (Z-hisobot), nasiya, hisobot
- **Tekshiruvchi (nazorat)** — dashboard (yashirilgan savdo + potensial soliq), bozor sxemasi, do'kon sahifasi, signallar, dalil to'plami
- **Super admin (panel)** — hisob ochish (login varaqasi), Excel import, tizim sozlamalari, audit

## Texnologiya
Django 5.1 + DRF (API-first) · PostgreSQL · Celery + Redis · HTMX + Alpine.js · Chart.js ·
custom dizayn tizimi (light/dark, o'zbek lotin/kirill). Barcha aktivlar **lokal**
(shrift/ikonka/JS/logo — CDN yo'q) — demo internetsiz ishlaydi.

## Ishga tushirish — lokal (Docker'siz)
Lokal PostgreSQL kerak. Baza va rol oching (nomlar `.env` bilan mos bo'lsin):
```bash
psql -U postgres -c "CREATE ROLE bozor LOGIN PASSWORD 'bozor';" -c "CREATE DATABASE bozor OWNER bozor;"
pip install -r requirements.txt
cp .env.example .env          # SECRET_KEY, DATABASE_URL ni to'ldiring (DEBUG=False)
# SECRET_KEY: python -c "import secrets; print(secrets.token_urlsafe(50))"  (prod kuchsiz kalit bilan ishga tushmaydi)
python manage.py migrate
python manage.py seed_demo --reset
python manage.py runserver
```
So'ng brauzerda: **http://localhost:8000/** (yoki `http://127.0.0.1:8000/`).
Kim login qilsa, o'sha odam roli interfeysiga tushadi.

## Ishga tushirish — Docker
```bash
cp .env.example .env
docker compose up --build     # web, db, redis, celery, beat, nginx
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo --reset
```
So'ng: **http://localhost/** (nginx 80-portda).

## Demo loginlar (bitta manzil, parol: `demo1234`)
| Login | Rol |
|-------|-----|
| `sotuvchi` | Sotuvchi |
| `nazorat` | Tekshiruvchi |
| `admin` | Super admin |
| `prokuror` | Prokuror (kuzatuvchi) — hamma narsani faqat ko'radi, har ko'rishi audit jurnalida |

Hammasi **bir xil manzildan** kiradi. Admin foydalanuvchilar ro'yxatida
**loginni** va o'zi bergan **vaqtinchalik parolni** (egasi almashtirguncha) ko'ra oladi — ko'rish audit
jurnaliga yoziladi. Egasi tanlagan parol ochiq saqlanmaydi (unutsa — "Parolni tiklash").
Production o'rnatish (HTTPS, birinchi admin, zaxira): [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Demo ssenariysi
1. **nazorat** bilan kiring → dashboard'da **yashirilgan savdo** va **potensial qo'shimcha soliq**
   (taxminiy) ko'rinadi; **bozor sxemasi**da yashiruvchi do'konlar qizil. Do'kon sahifasida
   rostlik tarkibi, grafik va **"Dalil to'plami"** (chop etsa bo'ladi).
2. **sotuvchi** bilan kiring (telefon rejimida) → **tez sotuv** (klaviatura + o'zbekcha
   savdolashish chegirmasi) yoki **skaner**; kirim (ro'yxatdan/qo'lda), qaytarish, kun yakuni;
   hisobotда rostlik va "qanday oshiraman" maslahati. Internet uzilsa sotuv telefonda
   saqlanib, tiklanganda avtomatik yuboriladi (offline navbat).
3. **admin** bilan kiring → hisob ochish → chop etiladigan login varaqasi; foydalanuvchilar
   (login, vaqtinchalik parol); tizim sozlamalari (rostlik chegaralari, soliq foizi); audit jurnali.

## Kunlik hisob-kitob
```bash
python manage.py recompute                 # bugungi rostlik + signal
python manage.py recompute --days 7        # oxirgi 7 kun
python manage.py recompute --date 2026-09-01
python manage.py simulate_camera           # kamerasiz jonli demo uchun soxta tashriflar
```
Production'da Celery beat buni avtomatik bajaradi (har 5 daqiqa / har kecha);
Redis bo'lmasa dev'da sinxron ishlaydi (`CELERY_TASK_ALWAYS_EAGER`).

## Rostlik formulasi (qisqacha)
`match(a,b)=min/max×100` — kam ham, ko'p ham yozsa tushadi. Qismlar: kassa
(deklaratsiya↔kiritilgan), kamera (tashrif×ulush×o'rtacha chek), qoldiq (kun yakuni),
narx (bozor medianasi). Og'irlikli o'rtacha; eng zaif qism sariq chegaradan past bo'lsa
umumiy ball cheklanadi. Barcha chegaralar `SystemSettings`'da (panelда) sozlanadi.
Yashirilgan savdo = max(kiritilgan, kamera, qoldiq) − deklaratsiya.

## Kamera keyin qo'shiladi
Backend kontrakti tayyor (`GET /api/cameras/config/`, `POST /api/events/`, heartbeat;
har kamera `token` bilan). AI worker skeleti: [`ai_worker/worker.py`](ai_worker/worker.py)
(RT-DETR/YOLOX + ByteTrack — Apache-2.0; Ultralytics YOLO va yuz tanish YO'Q).

## Sifat
`pytest` (105 test) · `ruff check` · `python manage.py check`. Loyiha xaritasi:
[`CLAUDE.md`](CLAUDE.md). To'liq talablar: [`docs/SPEC.md`](docs/SPEC.md).
