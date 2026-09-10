"""
Kamera / AI worker → backend hodisa qabul qilish API'si.

=============================================================================
 KAMERA INTEGRATSIYASI SHU YERDA ULANADI  (CLAUDE-CODE: camera integration seam)
=============================================================================
Kamera qo'shilganda, bozor serverida ishlaydigan AI worker quyidagicha yuboradi:

    POST /api/events/
    Header:  X-Camera-Token: <camera.ingest_token>
    Body (JSON):
      {
        "type": "visit",
        "shop_id": 12,
        "timestamp": "2026-09-10T14:03:00+05:00",
        "payload": {"dwell_seconds": 8, "track_id": "abc123"}
      }

Boshqa turlar:
  type="tamper"            payload: {kind, duration_seconds}
  type="sale_observation"  payload: {product_guess, confidence}

Worker hali yozilmagan — bu endpoint tayyor turadi. AI tomonini
CAMERA_INTEGRATION.md hujjatida bosqichma-bosqich yozib qo'ydik.
=============================================================================
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from cameras.models import Camera
from markets.models import Shop

from .models import CameraTamperEvent, CustomerVisit, SaleObservation
from .serializers import EventIngestSerializer


def _authenticate_camera(request):
    token = request.headers.get("X-Camera-Token", "")
    if not token:
        return None
    return Camera.objects.filter(ingest_token=token, is_active=True).first()


@api_view(["POST"])
@authentication_classes([])          # token header orqali autentifikatsiya
@permission_classes([AllowAny])
def ingest_event(request):
    camera = _authenticate_camera(request)
    if camera is None:
        return Response({"detail": "Kamera tokeni noto'g'ri."},
                        status=status.HTTP_401_UNAUTHORIZED)

    # Har qanday hodisa = kamera tirik. Heartbeat yangilaymiz.
    camera.last_heartbeat = timezone.now()
    camera.save(update_fields=["last_heartbeat"])

    ser = EventIngestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    etype = data["type"]
    ts = data["timestamp"]
    payload = data.get("payload") or {}

    shop = None
    if data.get("shop_id"):
        shop = Shop.objects.filter(pk=data["shop_id"]).first()
        if shop is None:
            return Response({"detail": "shop_id topilmadi."}, status=400)

    if etype == "visit":
        if shop is None:
            return Response({"detail": "visit uchun shop_id kerak."}, status=400)
        CustomerVisit.objects.create(
            shop=shop, camera=camera, timestamp=ts,
            dwell_seconds=int(payload.get("dwell_seconds", 0)),
            track_id=str(payload.get("track_id", "")),
        )
    elif etype == "tamper":
        CameraTamperEvent.objects.create(
            camera=camera, timestamp=ts,
            kind=payload.get("kind", CameraTamperEvent.Kind.OFFLINE),
            duration_seconds=int(payload.get("duration_seconds", 0)),
        )
    elif etype == "sale_observation":
        if shop is None:
            return Response({"detail": "sale_observation uchun shop_id kerak."}, status=400)
        SaleObservation.objects.create(
            shop=shop, camera=camera, timestamp=ts,
            product_guess=payload.get("product_guess", ""),
            confidence=float(payload.get("confidence", 0)),
        )

    return Response({"status": "ok"}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def camera_heartbeat(request):
    """AI worker tirikligini bildirish uchun (hodisasiz ham)."""
    camera = _authenticate_camera(request)
    if camera is None:
        return Response({"detail": "Kamera tokeni noto'g'ri."}, status=401)
    camera.last_heartbeat = timezone.now()
    camera.save(update_fields=["last_heartbeat"])
    return Response({"status": "ok"})
