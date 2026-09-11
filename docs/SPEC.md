# SPEC — Bozor Nazorat tizimi (to'liq talablar)

## 1. Maqsad
Bozordagi do'konlar savdosini nazorat qilish. Do'konlar chek bermaydi yoki kirimni
yashiradi. Tizim uch manbani solishtiradi va har do'konga **rostlik darajasi (%)** beradi:
1. **Sotuvchi kiritgani** — sotuvchi ilovasidagi kirim/sotuv/kun yakuni.
2. **Kassa / deklaratsiya** — boshida Excel'dan, keyin Soliq qo'mitasi API.
3. **Kamera + AI** — 1-bosqichda ulanmaydi; backend kontrakti tayyor (8-bo'lim).

Ular mos kelsa rostlik yuqori; mos kelmasa tekshiruvchiga **signal**.
**Tamoyil:** tizim natijasi — tekshiruvga yuborish uchun signal, jarima uchun dalil emas.
Yakuniy qarorni inspektor joyida tekshirgach qabul qiladi.

## 2. Interfeyslar (bitta backend, host bo'yicha)
- `sotuvchi.*` — telefon; katta tugmalar, sotuv 1–3 soniyada.
- `nazorat.*` — kompyuter; dashboard, xarita, do'kon sahifasi, signallar.
- `panel.*` — super admin; hisob ochish, import, sozlamalar, audit.

## 3. Texnologiya
Django + DRF (API-first, mobil keyin shu API'ga ulanadi). PostgreSQL (dev'da ham).
Celery + Redis (rostlik/narx fon vazifasi: har 5 daq va har kecha). HTMX + Alpine.js,
Chart.js. Barcha kutubxona/shrift/ikonka **lokal** (CDN yo'q, davlat tizimi tashqariga
ulanmaydi). Auth: sessiya + CSRF (bir domen); mobil uchun token tayyor, hozir yoqilmagan.
Deploy: Docker Compose (web/db/redis/celery/beat/nginx). Kod sifati: ruff+black, testlar,
biznes logika `services.py`'da.

## 4. Ma'lumot modeli
`Region → Market → Row`, `ShopCategory`, `ProductCategory` (umumiy — bozor narxi uchun),
`Shop` (raqam, STIR, egasi, kategoriya, qator, xarita o'rni, yopiq kunlar),
`User` (rol seller/inspector/superadmin, shop, is_shop_owner, assigned_markets,
must_change_password, blok maydonlari, telegram_id, language).
`Product` (do'kon, kategoriya, birlik, tannarx/sotish narxi, barkod, pack_coeff, kam qoldiq).
`StockIn`, `Sale`+`SaleItem` (rejim scan/quick, subtotal/discount/rounding/total, to'lov,
ulgurji, server_ts + client_ts + is_late), `SaleReturn`, `WriteOff` (foto majburiy),
`DailyClose`+`DailyCloseLine`, `Correction` (eski qiymat saqlanadi), `Debt`, `CashRecord` (source).
`Camera` (kind counter/overview/gate, rtsp, counter_zone, staff_zone, token, status, last_seen),
`CameraEvent` (type, count, payload, clip, ts). `MarketPrice`, `DailyScore` (agregat),
`Alert`, `Inspection`, `Appeal`. `SystemSettings` (yagona), `AuditLog`.
Barcha modelda `created_at`; pul yozuvlarida `PROTECT`, o'chirish yo'q (faqat Correction).

## 5. Biznes qoidalar
Pul — butun son (so'm). Miqdor — Decimal(3).
**Rostlik:** `match(a,b)=min/max×100`; kassa/kamera/qoldiq/narx qismlari; og'irlikli o'rtacha;
ma'lumoti yo'q qism chiqariladi; **eng zaif qism** sariq chegaradan past bo'lsa umumiy ball
≤ (o'sha qism + cap). Rang: ≥80 yashil, 50–80 sariq, <50 qizil (sozlanadi). Yopiq kunda signal yo'q.
**Chegirma:** butun chekka; tugmalar chek summasiga qarab; tannarxdan past mumkin emas
(noma'lum → maks 30%); yaxlitlash faqat pastga (≤1000), statistikaga kirmaydi; logika bitta
manbada (server+frontend). **Tezlik:** scan (barkod→chegirma→Sotildi) va quick (bir tugma).
Vaqt serverdan; kech kiritilsa belgilanadi. **Nazorat quroli:** o'xshash do'konlar solishtiruvi,
o'rtacha chegirma vs bozor, tannarxga yaqin sotuvlar, trend.
**Himoya:** yozuv o'chmaydi; o'z-o'zidan ro'yxat yo'q (admin ochadi, login=STIR-do'kon raqami);
5 xato → 15 daq blok; birinchi kirishda parol almashtirish; inspektor faqat o'z hududi; audit.

## 6. Interfeyslar tarkibi
**Sotuvchi:** bosh sahifa (bugungi savdo, rostlik, kam qoldiq), tez/skaner sotuv, kirim,
mahsulotlar, kun yakuni, qaytarish, hisobdan chiqarish (foto), nasiya, hisobot (rostlik grafigi
+ "qanday oshiraman"), e'tiroz; offline navbat.
**Tekshiruvchi:** dashboard (jami/xavf reytingi/signal lentasi/aniqlik %), bozor xaritasi
(qator, yashil/sariq/qizil), do'kon qidirish, do'kon sahifasi (rostlik tarkibi, kiritilgan vs
kassa vs kamera grafigi, o'xshashlar, chegirma, tannarxga yaqin, trend, signal/tuzatish/e'tiroz,
video dalil joyi), signallar + tekshiruv natijasi (foto), kameralar holati, hisobot + Excel.
**Super admin:** dashboard, hisob ochish (bittalab + Excel → chop etiladigan login varaqalari),
parol tiklash/blok, kassa Excel yuklash, sozlamalar (barcha chegaralar), audit.

## 7. Demo ma'lumot
`seed_demo --reset`: 1 viloyat, 1 bozor, 4 qator, 24 do'kon, 7 kunlik savdo; 3–4 yashiruvchi
(kassa/narx) — xaritada qizil. `simulate_camera`: soxta kamera hodisalari (API formatida).
Demo internetsiz ishlaydi.

## 8. Kamera — keyingi bosqich (backend tayyor)
Kontrakt (o'zgarmaydi): `GET /api/cameras/config/`, `POST /api/events/`, heartbeat
(X-Camera-Token). `CameraEvent` modeli, `camera_estimate` va `recompute_for_date` interfeysi.
`ai_worker/` (bozor serverida): RTSP substream → detektor → tracker → zona logikasi → events.
Model Apache-2.0 (RT-DETR/YOLOX/D-FINE + ByteTrack). **Ultralytics YOLO yo'q (AGPL).**
Birinchi funksiyalar: peshtaxta oldida 5+ soniya to'xtagan xaridor (chiziq kesish emas —
rastada eshik yo'q), kamera yopilishi (tamper), heartbeat. Sotuvchi zonasi sanalmaydi.
Keyin: ANPR (darvoza), tarozi OCR, mahsulot tanish (VLM, Qwen2.5-VL). **Yuzni tanish yo'q.**
Video bozordan chiqmaydi; markazga faqat hodisa. Panelда snapshotда zona chiziladi.
Shubhali hodisaning 10 soniyalik klipi — dalil.

## 9. Dizayn
Design tokenlar (light/dark, `data-theme`). Brend palitrasi (suzani indigo, g'isht, pista-yashil)
holat ranglaridan (yashil/sariq/qizil) ajratilgan. Iliq qum neytrallar. Tipografika: Spectral
(sarlavha) + Inter (matn), kirill glifli. Koshin naqsh faqat login/bo'sh holatlarda, nozik.
Lucide ikonka, Twemoji emoji (ozdan). Custom komponentlar (kalendar, select, toggle, modal,
toast) — ARIA + klaviatura. Responsive, ko'rinadigan fokus, prefers-reduced-motion, AA kontrast.

## 10. Yetkazish
Docker Compose bir buyruqda; migratsiya+seed+run; testlar o'tadi; README/CLAUDE.md/SPEC.md.
Bosqichlar: P0 poydevor · P1 dizayn · P2 sotuvchi · P3 nazorat · P4 panel · P5 kamera kontrakti ·
P6 Docker+ai_worker+hujjatlar — **bajarildi**.
