"""
Kamera / AI worker → backend kontrakti (O'ZGARMAYDIGAN interfeys).

Kamera qo'shilganda faqat `ai_worker` yoziladi; bu endpointlar o'zgarmaydi.

  GET  /api/cameras/config/        Header: X-Camera-Token   → worker konfiguratsiyasi
  POST /api/events/                Header: X-Camera-Token   → hodisa(lar) yuborish
  POST /api/cameras/heartbeat/     Header: X-Camera-Token   → tiriklik signali

Hodisa formati (POST /api/events/):
  bitta:   {"type","shop_id","timestamp","payload"}
  ko'p:    {"events": [ {...}, {...} ]}

type: visit | tamper | sale | gate_in | heartbeat
  visit    payload: {dwell_seconds, track_id}            shop_id majburiy
  tamper   payload: {kind: covered|moved|offline|blurred, duration_seconds}
  sale     payload: {product_guess, confidence}          shop_id majburiy
  gate_in  payload: {plate?, count}                       (darvoza)

Video bozordan chiqmaydi — faqat hodisa (raqam/JSON) yuboriladi. Shubhali
hodisaning klipi `clip` sifatida keyin biriktiriladi (dalil uchun).
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.format import to_int
from apps.shops.models import Shop

from .models import Camera, CameraEvent


def _auth(request):
    token = request.headers.get("X-Camera-Token", "")
    if not token:
        return None
    return Camera.objects.filter(token=token, is_active=True).select_related("market").first()


def _touch(camera, status=Camera.Status.ONLINE):
    camera.last_seen = timezone.now()
    camera.status = status
    camera.save(update_fields=["last_seen", "status"])


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def camera_config(request):
    """AI worker ishga tushganda konfiguratsiyani oladi (zonalar, do'konlar, chegaralar)."""
    camera = _auth(request)
    if camera is None:
        return Response({"detail": "Token noto'g'ri."}, status=401)
    _touch(camera)
    shops = Shop.objects.filter(pk=camera.shop_id) if camera.shop_id else Shop.objects.none()
    return Response(
        {
            "camera_id": camera.id,
            "name": camera.name,
            "kind": camera.kind,
            "rtsp_sub": camera.rtsp_sub,  # worker substream'ni o'qiydi
            "counter_zone": camera.counter_zone,  # xaridor sanaladigan zona
            "staff_zone": camera.staff_zone,  # sotuvchi zonasi — SANALMAYDI
            "min_dwell_seconds": settings.VISITOR_MIN_DWELL_SECONDS,
            "shops": [{"id": s.id, "number": s.number, "name": s.display_name} for s in shops],
        }
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def ingest_events(request):
    """Bitta yoki bir nechta hodisa qabul qiladi. Har qanday hodisa = kamera tirik."""
    camera = _auth(request)
    if camera is None:
        return Response({"detail": "Token noto'g'ri."}, status=401)

    data = request.data
    events = data.get("events") if isinstance(data, dict) and "events" in data else [data]
    if not isinstance(events, list):
        return Response({"detail": "events ro'yxat bo'lsin."}, status=400)
    if len(events) > MAX_BATCH:
        return Response({"detail": f"Bir so'rovda ko'pi bilan {MAX_BATCH} hodisa."}, status=400)
    now = timezone.now()
    created = 0
    skipped = 0
    tampered = False
    for ev in events:
        if not isinstance(ev, dict):
            skipped += 1
            continue
        etype = ev.get("type")
        if etype not in dict(CameraEvent.Type.choices):
            skipped += 1
            continue
        ts = _parse_ts(ev.get("timestamp"), now)
        if ts is None:
            # Kelajak yoki juda eski vaqt — kun ballarini orqaga/oldinga surib bo'lmasin
            skipped += 1
            continue
        # XAVFSIZLIK: hodisa do'koni kamera bozoriga/do'koniga bog'liq bo'lishi shart —
        # valid tokenli kamera boshqa do'kon uchun soxta hodisa yubora olmasin.
        if camera.shop_id:
            shop = camera.shop  # kameraga biriktirilgan do'kon (yuborilgan shop_id e'tiborsiz)
        elif ev.get("shop_id"):
            shop = Shop.objects.filter(
                pk=to_int(ev["shop_id"], 0) or 0, market_id=camera.market_id
            ).first()
        else:
            shop = None
        payload = ev.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        if etype == CameraEvent.Type.HEARTBEAT:
            continue  # heartbeat faqat last_seen ni yangilaydi (pastda)
        if etype == CameraEvent.Type.TAMPER:
            tampered = True
        # Manfiy/ulkan son kamera bahosini (va rostlikni) buzmasin
        count = to_int(payload.get("count", 1), 1)
        count = max(0, min(count if count is not None else 1, MAX_COUNT))
        CameraEvent.objects.create(
            camera=camera,
            shop=shop,
            type=etype,
            count=count,
            payload=payload,
            ts=ts,
        )
        created += 1

    _touch(camera, Camera.Status.TAMPERED if tampered else Camera.Status.ONLINE)
    return Response({"status": "ok", "created": created, "skipped": skipped}, status=201)


MAX_BATCH = 500  # bitta so'rovdagi hodisalar
MAX_COUNT = 50  # bitta hodisadagi odam soni (peshtaxta oldida)
TS_WINDOW = timedelta(days=1)  # qurilma vaqti server vaqtidan shuncha farq qilishi mumkin


def _parse_ts(raw, now):
    """Hodisa vaqti: bo'sh → hozir; noto'g'ri/juda uzoq → None (rad)."""
    if not raw:
        return now
    try:
        ts = parse_datetime(str(raw))
    except (ValueError, TypeError):
        return None
    if ts is None:
        return None
    if timezone.is_naive(ts):
        ts = timezone.make_aware(ts)
    if ts > now + timedelta(minutes=10) or ts < now - TS_WINDOW:
        return None
    return ts


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def heartbeat(request):
    camera = _auth(request)
    if camera is None:
        return Response({"detail": "Token noto'g'ri."}, status=401)
    _touch(camera)
    return Response({"status": "ok", "server_time": timezone.now().isoformat()})
