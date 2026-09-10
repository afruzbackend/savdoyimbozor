# CLAUDE.md — loyiha xaritasi (Claude Code uchun)

**Savdo Nazorat** — bozor savdosini AI orqali nazorat qilib, soliq deklaratsiyasi
bilan solishtiradigan va yashiruvchi do'konlarni signal beradigan Django tizimi.

## Muhim kontekst
- Til: interfeys **o'zbekcha** (lotin), kirill/rus qo'shiladi. Yangi matnlar o'zbekcha.
- **Kamera hozircha yo'q.** Sayt + PWA kamerasiz to'liq ishlaydi (sotuvchi savdoni
  qo'lda kiritadi). Kamera keyin qo'shiladi — ulanish nuqtalari tayyor.
- **Kamera integratsiyasini o'zgartirishdan oldin `CAMERA_INTEGRATION.md` ni o'qing.**
  Kodda belgi: `CAMERA-INTEGRATION` / `camera integration seam` (`events/api.py`).

## Ishga tushirish
```
python manage.py migrate
python manage.py seed_demo      # demo (loginlar: admin/rahbar/inspektor/sotuvchi, parol demo1234)
python manage.py runserver
python manage.py recompute      # kunlik statistika + signal
```
MVP bazasi: SQLite. Production: `.env` da `DB_ENGINE=postgres`.

## Applar
- `accounts` — `User` (AbstractUser) + rol (admin/manager/inspector/seller), bozor/do'kon biriktirish. Ruxsat asosi: `user.visible_markets()`.
- `markets` — `Market`, `Shop` (STIR, toifa), `ProductCategory` (`avg_ticket` kalibrlash uchun). `Shop.similar_shops()` — o'xshash do'konlar solishtiruvi.
- `cameras` — `Camera` (+ `ingest_token`, `is_online`). UI: holat ro'yxati.
- `events` — **AI hodisalari** (`CustomerVisit`, `CameraTamperEvent`, `SaleObservation`) + **sotuvchi kiritadigan** (`Sale`, `SaleItem`, `Return`, `StockWriteOff`). API: `events/api.py`.
- `analytics` — `Declaration`, `DailyShopStat`, `Alert`. Butun mantiq: `analytics/services.py` (peer_comparison, generate_alerts). Excel deklaratsiya yuklash.
- `inspections` — `Inspection` (natija tasdiq/noto'g'ri → AI aniqligini o'lchaydi).
- `reports` — yig'ma hisobot + Excel eksport (openpyxl).
- `audit` — `AuditLog` + `audit/middleware.py` (muhim amallarni yozadi).
- `dashboard` — rolga qarab bosh sahifa (INSTALLED_APPS'da emas, faqat urls/views).

## Konventsiyalar
- Frontend: HTMX + o'z CSS (`static/css/style.css`), Tailwind YO'Q. Chart.js va htmx **lokal** (`static/js/`) — CDN emas (internetsiz demo uchun).
- Shablonlar `templates/` (loyiha darajasida), app nomi bo'yicha papka.
- Pul: `DecimalField`. Vaqt: `USE_TZ=True`, `Asia/Tashkent`.
- Yangi model qo'shsangiz: `makemigrations` + `migrate` + admin'ga ro'yxat.
- Statistika o'zgartirsangiz — `analytics/services.py` da, keyin `recompute` bilan test.
