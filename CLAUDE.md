# CLAUDE.md — loyiha xaritasi (Claude Code uchun)

**Bozor Nazorat** — bozor savdosini uch manba (sotuvchi/kassa/kamera) bo'yicha
solishtirib rostlik darajasi beradigan va yashiruvchini signal beradigan Django tizimi.

## Muhim kontekst
- Interfeys tili **o'zbekcha** (lotin; kirill/rus i18n). Kod/model/o'zgaruvchi — inglizcha.
- **API-first**: biznes mantiq `services.py`'da; DRF/view faqat chaqiradi.
- **PostgreSQL** (SQLite ISHLATILMAYDI). Pul = butun son (so'm), Decimal(3) miqdor.
- Barcha aktivlar **lokal** (CDN yo'q): `static/fonts` (Inter+Spectral), `static/js`
  (alpine/htmx/chart), `static/icons/sprite.svg` (Lucide), `static/emoji` (Twemoji).
- **Kamerani o'zgartirishdan oldin** `apps/cameras/api.py` dagi kontrakt izohini o'qing.

## Ishga tushirish
`docker compose up --build` yoki lokal (README'ga qarang). Demo:
`seed_demo --reset` (loginlar admin/nazorat/sotuvchi, parol demo1234),
`simulate_camera` (kamerasiz jonli demo), `recompute` (rostlik+signal).

## Applar (`apps/`)
- `core` — SystemSettings (barcha chegaralar), AuditLog, TimeStampedModel, HostRouting + Audit middleware, panel (super admin) views.
- `accounts` — User(Role: superadmin/inspector/seller), blokli login, `visible_shops()` (ruxsat markazi), `services.py` (hisob ochish, login = STIR-do'kon raqami).
- `geo` — Region → Market → Row. `catalog` — ShopCategory, ProductCategory (bozor narxi uchun), Product. `shops` — Shop.
- `sales` — Sale/SaleItem, StockIn, SaleReturn, WriteOff, DailyClose, Debt; `services/pricing.py` (chegirma/yaxlitlash BITTA MANBA), `services/sales.py`; seller_views + api.
- `cash` — CashRecord (deklaratsiya; source: excel/tax_api/kassa).
- `cameras` — Camera, CameraEvent; `api.py` (kontrakt); `simulate_camera`.
- `analytics` — MarketPrice, DailyScore (agregat), Alert, Inspection, Appeal;
  `scoring/services.py` (rostlik dvigateli); inspector_views; Celery `tasks.py`.
- `api` — DRF router + endpointlarni yig'adi.

## Host routing
`config/settings/base.py`: HOST_PREFIX_MAP (sotuvchi→seller, nazorat→inspector, panel→panel).
`core/middleware.HostRoutingMiddleware` hostga qarab ROOT_URLCONF tanlaydi
(`config/urls_seller|inspector|panel.py`). Dev'da `*.localhost`.

## Rostlik formulasi — `apps/analytics/scoring/services.py`
```
match(a,b) = min(a,b)/max(a,b)*100         # kam ham, ko'p ham yozsa tushadi
kassa  = match(deklaratsiya, kiritilgan)
kamera = match(tashrif×buyer_ratio×o'rtacha_chek, kiritilgan)
narx   = 30-kunlik narx / bozor medianasi (≥0.8→100, ≤0.4→0, orada chiziqli)
Rostlik% = og'irlikli o'rtacha (ma'lumoti yo'q qism chiqariladi, og'irlik qayta taqsimlanadi)
Eng zaif qism sariq chegaradan past bo'lsa → umumiy ball ≤ (o'sha qism + weakest_part_cap)
Rang: ≥green yashil, ≥yellow sariq, aks holda qizil. Yopiq kunda signal yo'q.
```
Og'irlik/chegaralar `SystemSettings`'da (panelда tahrirlanadi). O'zgartirgach `recompute`.

## Chegirma/narx — `apps/sales/services/pricing.py` (bitta manba)
Butun chekka; tugmalar chek summasiga qarab; tannarxdan past mumkin emas (noma'lum → maks %);
yaxlitlash faqat pastga, statistikaga kirmaydi. Server tekshiradi, frontend shu qoidani ko'rsatadi.

## Kamera qo'shish tartibi (kontrakt o'zgarmaydi)
1. `/panel` → admin kamera qo'shadi (bozor, do'kon) → `token` beriladi (`/django-admin/` da ham).
2. `ai_worker/config.json` ga token + RTSP substream yoziladi.
3. Worker `GET /api/cameras/config/` (zonalar) → RTSP → detektor → tracker → zona/dwell →
   `POST /api/events/` (visit/tamper) + heartbeat. Faqat hodisa yuboriladi, video qolmaydi.
4. `apps/analytics/scoring/services._camera_estimate` avtomatik kamera qismini qo'shadi.
- Model: RT-DETR/YOLOX/D-FINE + ByteTrack (Apache-2.0). **Ultralytics YOLO YO'Q (AGPL).**
  **Yuzni tanish YO'Q** (biometrik). Sotuvchi zonasi (staff_zone) sanalmaydi.

## i18n (til)
- **O'zbek lotin↔kirill** — avtomatik transliteratsiya (`static/js/i18n.js`): lotin manba,
  kirill deterministik hosil bo'ladi (ikki katalog saqlanmaydi). Cookie `uilang="cyrl"`.
  Sidebar footer'da Lotin/Кирилл tugmasi. `[data-noloc]`, input, code, raqam tegilmaydi.
- **Rus tili** — gettext talab qiladi. Bu Windows mashinada `msgfmt/xgettext` YO'Q, shuning uchun
  `makemessages/compilemessages` ishlamaydi. GNU gettext o'rnatilgach: strings'ni `{% trans %}`/
  `gettext` bilan o'rash, `ru` katalogini tarjima qilish. Model verbose_name'lar allaqachon `gettext_lazy`.

## Konventsiyalar
- Shablonlar: har interfeys `templates/<iface>/base.html` (shell + nav) dan meros oladi.
  Umumiy: `base.html`, `shell.html`, `components/`.
- Chartga ma'lumot: view'da **dict** uzat + `{{ x|json_script:"id" }}` (json.dumps QILMANG — ikki marta kodlanadi).
- Yangi model → `makemigrations` + admin. Yangi env → `env(...)` da `default=` kalit so'z bilan.
- Test: `pytest` (narxlash testlari `apps/sales/tests/`). Sifat: `ruff check`, `black`.
- runserver `--noreload` bilan bo'lsa, kod/shablon o'zgargach QAYTA ishga tushiring.

## Backlog (keyingi)
- Kamera: ai_worker detektor/tracker (RT-DETR + ByteTrack), ANPR, tarozi OCR, VLM (Qwen2.5-VL).
- Telegram signal; Soliq API / virtual kassa / to'lov (Click/Payme) adapterlari.
- Qoldiq (stock) rostlik qismini DailyClose asosida to'liq ulash.
- Nazorat guruhi bilan pilot solishtiruvi (kamerali vs kamerasiz).
- ClickHouse'ga og'ir analitikani ko'chirish (DailyScore agregat tayyor).
