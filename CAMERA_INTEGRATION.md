# Kamera / AI integratsiyasi — bosqichma-bosqich reja

> Bu hujjat kamerani keyin qo'shish uchun. Sayt va ilova **kamerasiz ham to'liq
> ishlaydi** (sotuvchi savdoni qo'lda kiritadi). Kamera qo'shilganda faqat
> `visitor_count` va AI kuzatuvlari real ma'lumot bilan to'ladi — qolgan hamma
> narsa (dashboard, signal, hisobot, tekshiruv) o'zgarishsiz ishlayveradi.

## Backend allaqachon tayyor

Kamera tomoni ulanadigan barcha nuqtalar kodda yozib qo'yilgan:

| Nuqta | Fayl |
|-------|------|
| Kamera modeli + `ingest_token` | `cameras/models.py` |
| Hodisa qabul qilish API | `events/api.py` → `POST /api/events/` |
| Hodisa modellari (visit/tamper/observation) | `events/models.py` |
| Statistika hisoblash | `analytics/services.py` |

Kodda qidiruv uchun belgi: **`CAMERA-INTEGRATION`** va **`camera integration seam`**.

## AI worker → backend shartnomasi (API)

AI worker bozor serverida ishlaydi, video shu yerda qoladi (tashqariga chiqmaydi),
faqat **hodisa** (raqam/JSON) yuboriladi.

```
POST http://<server>/api/events/
Header:  X-Camera-Token: <camera.ingest_token>
Content-Type: application/json
```

**1. Xaridor tashrifi** (peshtaxta oldida ≥ 5 sek to'xtagan odam):
```json
{ "type": "visit", "shop_id": 12,
  "timestamp": "2026-09-10T14:03:00+05:00",
  "payload": { "dwell_seconds": 8, "track_id": "person-4471" } }
```

**2. Kamera buzilishi** (yopilgan/burilgan/o'chgan):
```json
{ "type": "tamper", "timestamp": "...",
  "payload": { "kind": "covered", "duration_seconds": 40 } }
```

**3. AI sotuv kuzatuvi** (mahsulot taxmini, video dalil uchun):
```json
{ "type": "sale_observation", "shop_id": 12, "timestamp": "...",
  "payload": { "product_guess": "pomidor", "confidence": 0.82 } }
```

**Heartbeat** (hodisasiz tiriklik signali, online/offline uchun):
```
POST /api/heartbeat/   Header: X-Camera-Token: <token>
```

Har qanday hodisa kelganda `camera.last_heartbeat` yangilanadi → UI'da online ko'rinadi.

## Kamerani ro'yxatga olish

1. `/admin/` → **Kameralar** → yangi kamera qo'shiladi (bozor, qamrovdagi do'konlar).
2. Yaratilganda avtomatik `ingest_token` beriladi (admin sahifasida ko'rinadi).
3. Shu tokenni AI worker konfiguratsiyasiga qo'yasiz.
4. Test: `curl -X POST .../api/heartbeat/ -H "X-Camera-Token: <token>"`.

## AI worker'ni yozish rejasi (keyingi bosqich)

Worker alohida jarayon (Python), Django'ga tegmaydi, faqat API'ga POST qiladi.

1. **Video olish** — `go2rtc` yoki OpenCV orqali RTSP oqim.
2. **Odam aniqlash + treklash** — YOLO (ultralytics) + ByteTrack. Har odamga `track_id`.
3. **Zona + to'xtash** — har do'kon peshtaxtasi oldiga poligon chiziladi (admin snapshotda).
   Odam zonada ≥ `VISITOR_MIN_DWELL_SECONDS` tursa → `visit` yuboriladi.
   Sotuvchi zonasi (peshtaxta ichi) sanashdan chiqariladi.
4. **Kamera buzilishi** — kadr qorayishi/o'zgarishi aniqlansa → `tamper`.
5. **(Ixtiyoriy) sotuv kuzatuvi** — qo'l harakati + mahsulot klassifikatsiyasi → `sale_observation` + 10 sek klip.

Kalibrlash: pilotda bir nechta halol do'kon tanlanadi, "1 xaridor ≈ X so'm"
koeffitsiyenti chiqariladi va `ProductCategory.avg_ticket` ga yoziladi.
Shundan keyin `estimated_sales = visitor_count × avg_ticket` real ishlaydi.

## Muhim: aniqlik chegarasi

Tizim har so'mni sanamaydi — maqsad **yashiruvchini topish**. Eng kuchli usul
o'xshash do'konlar bilan solishtirish (`analytics/services.peer_comparison`),
u faqat xaridor sonini talab qiladi. Batafsil mulohaza loyiha suhbatida.
