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

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
    created = 0
    tampered = False
    for ev in events:
        etype = ev.get("type")
        if etype not in dict(CameraEvent.Type.choices):
            continue
        ts = parse_datetime(ev["timestamp"]) if ev.get("timestamp") else timezone.now()
        # XAVFSIZLIK: hodisa do'koni kamera bozoriga/do'koniga bog'liq bo'lishi shart —
        # valid tokenli kamera boshqa do'kon uchun soxta hodisa yubora olmasin.
        if camera.shop_id:
            shop = camera.shop  # kameraga biriktirilgan do'kon (yuborilgan shop_id e'tiborsiz)
        elif ev.get("shop_id"):
            shop = Shop.objects.filter(pk=ev["shop_id"], market_id=camera.market_id).first()
        else:
            shop = None
        payload = ev.get("payload") or {}
        if etype == CameraEvent.Type.HEARTBEAT:
            continue  # heartbeat faqat last_seen ni yangilaydi (pastda)
        if etype == CameraEvent.Type.TAMPER:
            tampered = True
        CameraEvent.objects.create(
            camera=camera,
            shop=shop,
            type=etype,
            count=int(payload.get("count", 1)),
            payload=payload,
            ts=ts,
        )
        created += 1

    _touch(camera, Camera.Status.TAMPERED if tampered else Camera.Status.ONLINE)
    return Response({"status": "ok", "created": created}, status=201)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def heartbeat(request):
    camera = _auth(request)
    if camera is None:
        return Response({"detail": "Token noto'g'ri."}, status=401)
    _touch(camera)
    return Response({"status": "ok", "server_time": timezone.now().isoformat()})
