# Bozor Nazorat — tahlil (16.10.2026)

> Asosiy fokus hozir **do'kon tizimi (Savdoyim)**, bu loyiha ikkinchi navbatda.
> Do'kon tahlili: `savdoyim26.08/docs/TAHLIL_DOKON.md`.
> [T] = manba bilan tasdiqlangan, [B] = baho. Qonuniy xulosalarni yurist bilan tasdiqlang.

## 1. Qisqa xulosa
- Kod yaxshi qurilgan: ~14.8k qator, **468 test o'tadi** (Python 3.11, lokal PostgreSQL).
  Docker, nginx TLS, Celery, `preflight`, zaxira, 2FA va throttling bor.
- Kamera/AI qismi mexanik jihatdan tayyor, lekin **haqiqiy kamerada hech qachon sinalmagan**,
  aniqligi noma'lum.
- **Davlat o'zining "E-bozor" platformasini qilyapti** (VMQ №358, 02.07.2026, operatori Soliq
  qo'mitasi). Uning ilovasida **"Piskent dehqon bozori" MChJ (372 do'kon)** ham bor [T].
  Shuning uchun davlatga to'g'ridan-to'g'ri sotish deyarli real emas.
- Real xaridor — **bozor operatori kompaniyasi**. Qonun bo'yicha u bozorni raqamlashtirishi va
  E-bozor bilan integratsiya qilishi shart, buni **o'z mablag'i hisobidan** qiladi [T].

## 2. Shoshilinch ishlar
1. **GitHub repo ochiq** — rostlik formulasi, chegaralar va kamera mantig'i hammaga ko'rinadi.
   Uni **Private** qiling (Settings → Change visibility). Tarixda sir topilmadi.
2. **Bitta tashrif "qizil" signal beradi**: `apps/analytics/scoring/services.py:540`
   (`strong = bool(visits)`). Bitta soxta aniqlash bo'lsa ham nol-savdo kuni qizil alert va
   Telegram xabar ketadi.
3. **"Jinoyat darajasi" yorlig'i** (`apps/analytics/fines.py:11-17`) tasdiqlanmagan kamera
   bahosidan chiqadi. AI bahosini dalil sifatida ishlatishga qonuniy asos topilmadi [T].
   Operatorga ko'rsatiladigan versiyadan olib tashlang.
4. **Kamera o'lik bo'lsa ham "ONLINE" ko'rinadi** (`ai_worker/worker.py:403-422` heartbeat
   oqim tirikligini tekshirmaydi). `tamper` hodisasi umuman yuborilmaydi.
5. Kamera sonlarini kimgadir ko'rsatishdan oldin **2 hafta qo'lda sanash bilan solishtiring**
   (3–5 rasta).

## 3. Kod topilmalari (o'rta/past)
- Ochiq matnda saqlanadi: vaqtinchalik parol (`accounts/models.py:63-67`), TOTP siri (`:69`),
  RTSP manzil va kamera tokenlari (`cameras/models.py:46-52`).
- Xodimlar uchun 2FA standart holatda o'chiq (`core/models.py:98`).
- CSP `'unsafe-inline' 'unsafe-eval'` ga ruxsat beradi (`config/settings/base.py:141`).
- Telegram orqali ism va ayblov sababi chet el serveriga ketadi (`analytics/notifications.py:36-42`),
  bu `DEPLOY.md` dagi "ma'lumot chetga chiqmaydi" degan qoidaga zid.
- Audit log o'zgartirishdan himoyalanmagan, ombor zanjiri kalitsiz SHA-256.
- Ma'lumotni saqlash muddati va o'chirish siyosati yo'q.
- Mobil operator NAT'i tufayli IP bo'yicha bloklash ko'p sotuvchini birdan to'xtatib qo'yishi mumkin.
- CI yo'q. README'da "105 test" deyilgan, aslida 468 ta.

## 4. Kamera pipeline
- **Ishlaydi:** RTSP → HOG yoki ONNX → IOU tracker → zona/dwell → `POST /api/events/`.
- **Muammolar:**
  - HOG peshtaxta va shift ko'rinishida yomon ishlaydi.
  - Track birinchi kadrda yo'qolsa tashlab yuboriladi (`worker.py:351-353`).
  - Zona bo'lmasa sotuvchi ham sanaladi (`:251`).
  - ONNX dekoder faqat YOLOX uchun.
  - Xato javoblarda hodisa jim yo'qoladi.
  - Navbat xotirada turadi, qayta ishga tushganda yo'qoladi.

## 5. Bozor va qonun [T]
- E-bozor: sinov 01.10.2026 gacha, integratsiya 01.12.2026 gacha, to'liq ishga tushish 01.03.2027.
  Ro'yxatdagi bozorlar 01.09.2026 gacha raqamlashtirilishi kerak edi.
  Qamrov: 280 yoki 300+ bozor (manbalar har xil).
- Har bir savdo nuqtasiga onlayn kassa yoki QR yorliq kerak. Har bir bozorga soliq xodimi biriktiriladi.
- Soliq qo'mitasida o'z AI'si bor (ai.soliq.uz, kompyuter ko'rish) — ichki raqobat.
- **Davlat xaridi:**
  - To'g'ridan-to'g'ri shartnomalar deyarli yopilgan (Farmon №259, 26.12.2025).
  - AI tizimlar reyestri (VMQ №510, 22.09.2026, ai.gov.uz): 2 500 BHM gacha xarid mumkin, lekin
    Kiberxavfsizlik markazi xulosasi va MChJ kerak. Portal 01.02.2027 gacha ishga tushadi.
  - Davlat tizimlari uchun ekspertiza majburiy (ZRU-764, VMQ 4328).
- **Bozorlar xususiylashtirilyapti** (Toshkentda 35 ta bozor sotuvda). Bu xususiy operatorga
  sotish imkoniyatini oshiradi.
- **Shaxsiy ma'lumotlar:** ZRU-1125 (26.03.2026) dan keyin faqat biometrik ma'lumot O'zbekistonda
  saqlanishi shart. Yuzni tanimaslik (hozirgi dizayn) biometrik rejimdan qochishga yordam beradi.
  Davlat bilan ishlaganda esa baribir lokal hosting talab qilinadi [B].
- **Tijorat analogi:** TASS Vision (Toshkent) do'konlarga AI tashrif kameralarini oyiga $29–119 dan
  sotadi, 2000+ do'kon.
- Sotuv sikli 6–18 oy [B]. Hokimiyatlar to'lovni bir yildan ortiq kechiktirgan holatlar bor [B].

## 6. Strategiya
- **Do'kon mahsuloti bilan bir brendda birlashtirmang.** "Sotuvchini tekshiradigan" tizim
  Savdoyim'ga bo'lgan ishonchni buzadi.
- **Pozitsiya:** "bozor operatori konsoli". Ichida rasta reyestri, ijara va QR to'lovlari, parkovka,
  xavfsizlik kameralari va E-bozor'ga toza ma'lumot oqimi bo'ladi.
  Prokuror roli va "jinoyat darajasi" bu taklifga kirmaydi.
- **Birinchi qadam — Piskent dehqon bozori MChJ direktori bilan bitta suhbat.** Undan so'raladigan savollar:
  - E-bozor uchun vendor tanlab bo'lindimi?
  - Kiberxavfsizlik ekspertizasidan o'tdimi?
  - Nima yetishmayapti?
- Shu javobga qadar yangi funksiya qo'shmang. Hozircha loyiha **muzlatiladi**, kuch do'kon tizimiga
  sarflanadi.
