"""
AI worker — bozor serverida ishlaydigan alohida jarayon.

Ishlaydigan SKELET: thread'lar, kadr to'plash (batch), heartbeat, hodisa navbati va
backend'ga yuborish TAYYOR. Faqat `Detector.detect()` va `Tracker` yozilmagan
(NotImplementedError) — ular kamera bosqichida qo'shiladi.

Model litsenziyasi: RT-DETR / YOLOX / D-FINE + ByteTrack (Apache-2.0).
Ultralytics YOLO ISHLATILMAYDI (AGPL-3.0). Yuzni tanish YO'Q (biometrik).
Video bozordan chiqmaydi — markazga faqat hodisa (JSON) yuboriladi.

Ishga tushirish:
    pip install -r ai_worker/requirements.txt
    python ai_worker/worker.py --config ai_worker/config.json
"""
from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # skelet importi test uchun buzilmasin
    requests = None


# ============================================================================
#  Konfiguratsiya
# ============================================================================
@dataclass
class CameraConf:
    token: str
    rtsp_sub: str = ""
    # Backend /api/cameras/config/ dan to'ldiriladi:
    camera_id: int | None = None
    counter_zone: list = field(default_factory=list)
    staff_zone: list = field(default_factory=list)
    min_dwell_seconds: int = 5
    shops: list = field(default_factory=list)


@dataclass
class WorkerConf:
    backend_url: str
    cameras: list[CameraConf]
    batch_seconds: float = 5.0
    heartbeat_seconds: float = 30.0


def load_config(path: str) -> WorkerConf:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    cams = [CameraConf(**c) for c in raw["cameras"]]
    return WorkerConf(backend_url=raw["backend_url"].rstrip("/"), cameras=cams,
                      batch_seconds=raw.get("batch_seconds", 5.0),
                      heartbeat_seconds=raw.get("heartbeat_seconds", 30.0))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
#  Detektor va tracker — KAMERA BOSQICHIDA YOZILADI
# ============================================================================
class Detector:
    """Odam aniqlash. RT-DETR / YOLOX (Apache-2.0) bilan almashtiriladi."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path

    def detect(self, frame):
        """frame → [ (x1,y1,x2,y2, score), ... ]  (odam ramkalari)."""
        raise NotImplementedError(
            "Detektor hali ulanmagan. RT-DETR yoki YOLOX (Apache-2.0) modelini "
            "shu yerga ulang. Ultralytics YOLO ishlatilmaydi (AGPL-3.0).")


class Tracker:
    """ByteTrack (Apache-2.0) bilan almashtiriladi — har odamga barqaror track_id."""

    def update(self, detections):
        raise NotImplementedError("Tracker (ByteTrack) hali ulanmagan.")


def point_in_zone(cx, cy, zone) -> bool:
    """Nuqta poligon ichidami (ray casting). Zonalar 0..1 normallashgan."""
    if not zone:
        return True
    inside = False
    n = len(zone)
    j = n - 1
    for i in range(n):
        xi, yi = zone[i]
        xj, yj = zone[j]
        if ((yi > cy) != (yj > cy)) and (cx < (xj - xi) * (cy - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


# ============================================================================
#  Kamera oqimi (bitta thread)
# ============================================================================
class CameraWorker(threading.Thread):
    def __init__(self, conf: CameraConf, out_queue: queue.Queue, stop: threading.Event):
        super().__init__(daemon=True, name=f"cam-{conf.camera_id or conf.token[:6]}")
        self.conf = conf
        self.q = out_queue
        self.stop = stop
        self.detector = Detector()
        self.tracker = Tracker()
        self.seen_tracks: dict = {}  # track_id -> {enter_ts, counted}

    def run(self):
        # Haqiqiy holatda: cap = cv2.VideoCapture(self.conf.rtsp_sub)
        # Bu yerda kadr o'qish + detect + track + zona/dwell mantig'i bo'ladi.
        while not self.stop.is_set():
            try:
                self._process_frame(frame=None)
            except NotImplementedError:
                # Skelet rejimi: detektor yo'q — jim kutamiz (demo simulate_camera bilan)
                time.sleep(1.0)
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] xato: {e}")
                time.sleep(1.0)

    def _process_frame(self, frame):
        """Bitta kadr: aniqlash → treklash → zona/dwell → hodisa navbatiga."""
        detections = self.detector.detect(frame)      # NotImplementedError (skelet)
        tracks = self.tracker.update(detections)
        shop_id = self.conf.shops[0]["id"] if self.conf.shops else None
        for tr in tracks:
            cx, cy = tr["cx"], tr["cy"]
            if point_in_zone(cx, cy, self.conf.staff_zone):
                continue  # sotuvchi zonasi — sanalmaydi
            if not point_in_zone(cx, cy, self.conf.counter_zone):
                continue
            rec = self.seen_tracks.setdefault(tr["id"], {"enter": time.time(), "counted": False})
            dwell = time.time() - rec["enter"]
            if not rec["counted"] and dwell >= self.conf.min_dwell_seconds:
                rec["counted"] = True
                self.q.put({"type": "visit", "shop_id": shop_id, "timestamp": now_iso(),
                            "payload": {"dwell_seconds": int(dwell), "track_id": str(tr["id"])}})


# ============================================================================
#  Yuboruvchi (batch) va heartbeat
# ============================================================================
class Sender(threading.Thread):
    def __init__(self, conf: WorkerConf, token_by_cam: dict, q: queue.Queue, stop: threading.Event):
        super().__init__(daemon=True, name="sender")
        self.conf = conf
        self.q = q
        self.stop = stop
        self.token = next(iter(token_by_cam.values())) if token_by_cam else ""

    def run(self):
        while not self.stop.is_set():
            time.sleep(self.conf.batch_seconds)
            batch = []
            while not self.q.empty() and len(batch) < 200:
                batch.append(self.q.get())
            if not batch:
                continue
            self._post({"events": batch})

    def _post(self, body):
        if requests is None:
            print("requests o'rnatilmagan — yuborilmadi:", len(body["events"]))
            return
        try:
            r = requests.post(f"{self.conf.backend_url}/api/events/",
                              json=body, headers={"X-Camera-Token": self.token}, timeout=8)
            if r.status_code >= 300:
                print("Backend xatosi:", r.status_code, r.text[:120])
        except requests.RequestException as e:
            print("Yuborishда xato (navbatda saqlanadi):", e)
            for ev in body["events"]:  # keyingi urinishga qaytaramiz
                self.q.put(ev)


class Heartbeat(threading.Thread):
    def __init__(self, conf: WorkerConf, stop: threading.Event):
        super().__init__(daemon=True, name="heartbeat")
        self.conf = conf
        self.stop = stop

    def run(self):
        while not self.stop.is_set():
            for cam in self.conf.cameras:
                if requests is None:
                    break
                try:
                    requests.post(f"{self.conf.backend_url}/api/cameras/heartbeat/",
                                  headers={"X-Camera-Token": cam.token}, timeout=5)
                except requests.RequestException:
                    pass
            self.stop.wait(self.conf.heartbeat_seconds)


def fetch_remote_config(conf: WorkerConf):
    """Har kamera uchun backend'dan zonalar/do'konlarni oladi."""
    if requests is None:
        return
    for cam in conf.cameras:
        try:
            r = requests.get(f"{conf.backend_url}/api/cameras/config/",
                             headers={"X-Camera-Token": cam.token}, timeout=8)
            if r.ok:
                d = r.json()
                cam.camera_id = d.get("camera_id")
                cam.counter_zone = d.get("counter_zone", [])
                cam.staff_zone = d.get("staff_zone", [])
                cam.min_dwell_seconds = d.get("min_dwell_seconds", 5)
                cam.shops = d.get("shops", [])
                cam.rtsp_sub = cam.rtsp_sub or d.get("rtsp_sub", "")
        except requests.RequestException as e:
            print(f"Config olinmadi ({cam.token[:6]}): {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="ai_worker/config.json")
    args = ap.parse_args()

    conf = load_config(args.config)
    fetch_remote_config(conf)

    stop = threading.Event()
    q: queue.Queue = queue.Queue()
    token_by_cam = {c.camera_id or i: c.token for i, c in enumerate(conf.cameras)}

    threads = [Sender(conf, token_by_cam, q, stop), Heartbeat(conf, stop)]
    threads += [CameraWorker(c, q, stop) for c in conf.cameras]
    for t in threads:
        t.start()

    print(f"AI worker ishga tushdi: {len(conf.cameras)} kamera. To'xtatish: Ctrl+C")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        print("To'xtatilmoqda...")


if __name__ == "__main__":
    main()
