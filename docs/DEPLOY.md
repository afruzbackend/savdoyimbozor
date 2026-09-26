# Bozor Nazorat — production'ga o'rnatish (davlat darajasi)

Bu hujjat **haqiqiy** o'rnatish uchun. Lokal demo (`seed_demo`, http://localhost) — README'da.

> **Qizil chiziqlar**
> - Production bazada `seed_demo` **HECH QACHON** ishga tushirilmaydi (demo loginlar, parol `demo1234`).
> - Faqat HTTPS. `docker-compose.prod.yml` HTTPS'siz ishga tushmaydi.
> - `.env`, TLS kalitlari, zaxira fayllari git'ga va obrazga tushmaydi.
> - Fuqarolarning shaxsga doir ma'lumotlari (F.I.O., telefon, STIR) **O'zbekiston hududidagi**
>   serverlarda saqlanadi ("Shaxsga doir ma'lumotlar to'g'risida"gi Qonun talabi). Xorijiy bulut,
>   xorijiy Sentry/monitoring ishlatilmaydi — xatolar kuzatuvi uchun o'z serverimizdagi GlitchTip.

## 1. Server
| | Pilot (1–2 bozor, ≤500 do'kon) | Viloyat |
|---|---|---|
| CPU / RAM | 4 vCPU / 8 GB | 8 vCPU / 16 GB |
| Disk | 100 GB SSD (fotolar o'sadi) | 500 GB SSD |
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |

- Docker Engine + Docker Compose plagini.
- Tashqariga faqat **80** (sertifikat yangilash + yo'naltirish) va **443** ochiq. SSH — faqat kalit bilan,
  parol bilan kirish o'chiq, IP cheklovli. PostgreSQL/Redis portlari tashqariga OCHILMAYDI (compose shunday).
- Vaqt: `timedatectl set-timezone Asia/Tashkent`, NTP yoqilgan (sotuv vaqti va audit shunga tayanadi).

## 2. Domen va TLS sertifikat
1. DNS: `bozor.soliq.uz` → server IP.
2. Sertifikat (davlat CA yoki Let's Encrypt) → `docker/certs/fullchain.pem` va `docker/certs/privkey.pem`
   (`chmod 600 privkey.pem`). Let's Encrypt misoli (80-port bo'sh vaqtda, birinchi marta):
   ```bash
   sudo certbot certonly --standalone -d bozor.soliq.uz
   sudo cp /etc/letsencrypt/live/bozor.soliq.uz/{fullchain,privkey}.pem docker/certs/
   ```
   Yangilash (webroot, ishlab turganda): `certbot renew --webroot -w docker/acme` va nginx'ni qayta yuklash
   (`docker compose exec nginx nginx -s reload`) — cron'ga qo'ying.

## 3. `.env`
```bash
cp .env.example .env && chmod 600 .env
```
Majburiy (bo'sh bo'lsa `docker-compose.prod.yml` ishga tushmaydi):

| O'zgaruvchi | Qiymat |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` — yangi, 50+ belgi |
| `ALLOWED_HOSTS` | `bozor.soliq.uz` |
| `CSRF_TRUSTED_ORIGINS` | `https://bozor.soliq.uz` |
| `PUBLIC_BASE_URL` | `https://bozor.soliq.uz` (xaridor QR cheki) |
| `DB_PASSWORD` | kuchli parol (20+ belgi) |
| `BACKUP_UPLOAD_CMD` | masalan `rclone copy {path} offsite:bozor-backup` — **boshqa binodagi** saqlash joyi |

Tavsiya: `SENTRY_DSN` (o'z GlitchTip), `HEALTH_TOKEN`, `APP_RELEASE`, `TELEGRAM_BOT_TOKEN`,
soliq integratsiyasi (`TAX_ADAPTER` ...). Hammasi `.env.example` da izohi bilan.

## 4. Ishga tushirish
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps        # hammasi "healthy/running"
curl -I https://bozor.soliq.uz/healthz/                                   # 200
```
Migratsiya va statik fayllar `web` konteyneri ishga tushganda avtomatik (`RUN_MIGRATIONS=1`).
Konteynerlar **root emas** (uid 10001) ishlaydi.

Qulaylik uchun: `alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'`.

## 5. Birinchi admin
```bash
dc exec web python manage.py createsuperuser
```
- Login — faqat raqam emas, istalgan (masalan `admin.tashkent`). Parol kamida 12 belgi.
- Birinchi kirishda **ikki bosqichli himoya (2FA)** ni ulang (Profil → 2FA), so'ng Panel → Sozlamalar →
  «Admin, tekshiruvchi va prokurorga ikki bosqichli himoya (2FA) majburiy» ni yoqing.
- Qolgan hisoblar faqat panel orqali (Hisob ochish / Do'kon import) — chop etiladigan login varaqasi.
  Vaqtinchalik parol birinchi kirishda almashtiriladi; egasi tanlagan parol **hech kimga ko'rinmaydi**
  (unutsa — admin "Parolni tiklash").

## 6. Boshlang'ich sozlash (panel)
1. Bozorlar → viloyat, bozor, qatorlar.
2. Savdo turlari → har tur uchun **xaridor ulushi** (kamera bahosi). Pilotning birinchi 2–4 haftasida
   bo'sh qoldiring — "Ma'lumot bo'yicha" tavsiyasi paydo bo'lgach kiriting.
3. Mahsulot turlari → variant turi, birlik, chirish me'yori (standartlar turga qarab qo'yilgan).
4. Do'kon import (Excel) → login varaqalarini chop etib tarqating.
5. Sozlamalar → rostlik chegaralari, og'irliklar, signal chegaralari.

## 7. Zaxira va tiklash
- Har kecha 02:30 (Celery beat): baza (`bozor-db-*.sql.gz`) + fotolar (`bozor-media-*.tar.gz`) +
  SHA-256, oxirgi 14 tasi serverda, har biri `BACKUP_UPLOAD_CMD` bilan tashqariga.
- Qo'lda: `dc exec celery python manage.py backup`
- **Tiklashni har chorakda sinab ko'ring** (alohida serverda):
  ```bash
  gunzip -c bozor-db-YYYYMMDD-HHMM.sql.gz | dc exec -T db psql -U bozor -d bozor
  dc cp bozor-media-YYYYMMDD-HHMM.tar.gz web:/tmp/ && dc exec web tar -xzf /tmp/bozor-media-YYYYMMDD-HHMM.tar.gz -C /app
  ```
  Tiklangach: Nazorat → Ombor → do'kon sahifasida "Jurnal butun" (xesh zanjiri) tekshiriladi.

## 8. Monitoring
- `/healthz/` — baza, kesh, Celery (tashqi uptime monitori har 1 daqiqada). Batafsil javob:
  `X-Health-Token: $HEALTH_TOKEN`.
- Xatolar — `SENTRY_DSN` (o'z GlitchTip). Loglar: `dc logs -f web celery beat`.
- Audit jurnali (panel) — kim nimani ko'rdi/o'zgartirdi; prokuror ko'rishlari ham.

## 9. Yangilash
```bash
git pull                       # yoki relizni ko'chiring
pip-audit -r requirements.txt  # (ixtiyoriy, CI'da) ma'lum zaifliklar yo'qligini tekshirish
dc build && dc up -d           # migratsiya avtomatik
```
Oldin zaxira oling. Orqaga qaytish: oldingi obraz tegi + o'sha kungi zaxira.

## 10. Topshirishdan oldin tekshiruv ro'yxati
- [ ] `https://` ochiladi, `http://` yo'naltiradi, sertifikat amal qiladi
- [ ] `dc exec web python manage.py check --deploy` — muammo yo'q
- [ ] `seed_demo` ishlatilmagan (demo loginlar yo'q: `sotuvchi`, `nazorat`, `admin`, `prokuror`)
- [ ] Admin va barcha xodimlarda 2FA yoqilgan
- [ ] Zaxira tashqariga ketdi (jurnalda "tashqariga yuborildi"), tiklash sinab ko'rilgan
- [ ] `/healthz/` monitoringga ulangan, xato kuzatuvi ishlaydi
- [ ] Server O'zbekiston hududida; SSH kalit bilan; faqat 80/443 ochiq
