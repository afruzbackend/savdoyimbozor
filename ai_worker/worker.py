"""
AI worker — bozor serverida ishlaydigan alohida jarayon.

TO'LIQ ISHLAYDI: RTSP oqim o'qish (OpenCV), odam aniqlash, treklash, zona/dwell
bo'yicha tashrif sanash, batch/heartbeat va backend'ga yuborish.

Detektor:
  - model_path BO'SH  -> OpenCV HOG odam detektori (model fayl kerak emas, darrov
    ishlaydi, offline). Pilot uchun yetarli.
  - model_path (ONNX) -> YOLOX / RT-DETR (Apache-2.0) onnxruntime bilan — aniqroq.
Tracker: yengil IOU-tracker (keyin ByteTrack bilan almashtirish mumkin).
Ultralytics YOLO ISHLATILMAYDI (AGPL-3.0). Yuzni tanish YO'Q (biometrik).
Video bozordan chiqmaydi — markazga faqat hodisa (JSON) yuboriladi.

Ishga tushirish (bozor mini-PC'sida):
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
from datetime import UTC, datetime

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
    # Detektor sozlamalari (ixtiyoriy). model_path bo'sh bo'lsa OpenCV HOG ishlatiladi
    # (model fayl kerak emas, darrov ishlaydi). ONNX (YOLOX/RT-DETR, Apache-2.0)
    # ishlatmoqchi bo'lsangiz model_path bering.
    model_path: str = ""
    input_size: int = 640
    conf_threshold: float = 0.0  # 0 => detektor turiga qarab standart (HOG .5 / ONNX .35)
    person_class_id: int = 0
    process_fps: float = 4.0  # sekundiga necha kadr tahlil qilinadi (yuk kamayadi)
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
    return WorkerConf(
        backend_url=raw["backend_url"].rstrip("/"),
        cameras=cams,
        batch_seconds=raw.get("batch_seconds", 5.0),
        heartbeat_seconds=raw.get("heartbeat_seconds", 30.0),
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ============================================================================
#  Detektor va tracker — KAMERA BOSQICHIDA YOZILADI
# ============================================================================
class Detector:
    """Odam aniqlash. Ikki yo'l:

    1) model_path BO'SH  -> OpenCV HOG odam detektori (model fayl kerak emas, darrov
       ishlaydi, offline, BSD litsenziya). Pilot/demo uchun yetarli.
    2) model_path BERILGAN (ONNX) -> YOLOX/RT-DETR (Apache-2.0) onnxruntime bilan —
       aniqroq. Ultralytics YOLO ISHLATILMAYDI (AGPL). Yuz tanish YO'Q.

    Qaytadi: [(x1, y1, x2, y2, score), ...] — piksel koordinatalarida odam ramkalari.
    """

    def __init__(self, conf: CameraConf | None = None):
        self.model_path = getattr(conf, "model_path", "") if conf else ""
        self.input_size = getattr(conf, "input_size", 640) if conf else 640
        self.person_class = getattr(conf, "person_class_id", 0) if conf else 0
        thr = getattr(conf, "conf_threshold", 0.0) if conf else 0.0
        self.mode = None
        self._hog = None
        self._sess = None
        self._inp = None
        self.available = False
        # ONNX yo'li
        if self.model_path:
            try:
                import onnxruntime as ort  # type: ignore

                self._sess = ort.InferenceSession(
                    self.model_path, providers=["CPUExecutionProvider"]
                )
                self._inp = self._sess.get_inputs()[0].name
                self.mode = "onnx"
                self.conf = thr or 0.35
                self.available = True
                print(f"Detektor: ONNX ({self.model_path})")
                return
            except Exception as e:  # noqa: BLE001
                print(f"ONNX yuklanmadi ({e}) — HOG'ga o'tamiz.")
        # HOG yo'li (standart)
        try:
            import cv2  # type: ignore

            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self.mode = "hog"
            self.conf = thr or 0.5
            self.available = True
            print("Detektor: OpenCV HOG (model fayl kerak emas)")
        except Exception as e:  # noqa: BLE001
            print(f"OpenCV yo'q — detektor ishlamaydi: {e}")

    def detect(self, frame):
        if not self.available or frame is None:
            raise NotImplementedError("Detektor mavjud emas (opencv/onnxruntime o'rnating).")
        if self.mode == "hog":
            return self._detect_hog(frame)
        return self._detect_onnx(frame)

    def _detect_hog(self, frame):

        rects, weights = self._hog.detectMultiScale(
            frame, winStride=(8, 8), padding=(8, 8), scale=1.05
        )
        out = []
        for (x, y, w, h), score in zip(rects, weights, strict=False):
            s = float(score) if hasattr(score, "__float__") else float(score[0])
            if s >= self.conf:
                out.append((int(x), int(y), int(x + w), int(y + h), s))
        return out

    def _detect_onnx(self, frame):
        """YOLOX-uslubidagi ONNX chiqishi: [N, 5+num_classes] (cx,cy,w,h,obj,cls...)."""
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        h0, w0 = frame.shape[:2]
        size = self.input_size
        r = min(size / h0, size / w0)
        nw, nh = int(round(w0 * r)), int(round(h0 * r))
        resized = cv2.resize(frame, (nw, nh))
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        canvas[:nh, :nw] = resized
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32)  # BGR->RGB, CHW
        out = self._sess.run(None, {self._inp: blob})[0]
        preds = out[0] if out.ndim == 3 else out
        boxes = []
        for p in preds:
            if len(p) < 6:
                continue
            obj = p[4]
            cls_scores = p[5:]
            cid = int(np.argmax(cls_scores))
            score = float(obj * cls_scores[cid])
            if cid != self.person_class or score < self.conf:
                continue
            cx, cy, w, hh = p[0], p[1], p[2], p[3]
            x1 = (cx - w / 2) / r
            y1 = (cy - hh / 2) / r
            x2 = (cx + w / 2) / r
            y2 = (cy + hh / 2) / r
            boxes.append((int(x1), int(y1), int(x2), int(y2), score))
        return _nms(boxes, 0.45)


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a[:4]
    bx1, by1, bx2, by2 = b[:4]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _nms(boxes, thr):
    boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
    keep = []
    while boxes:
        best = boxes.pop(0)
        keep.append(best)
        boxes = [b for b in boxes if _iou(best, b) < thr]
    return keep


class Tracker:
    """Yengil IOU-tracker — har odamga barqaror track_id (ByteTrack keyin almashtiriladi).

    Sanash uchun yetarli: ketma-ket kadrlarда ramkalarни IOU bo'yicha bog'laydi.
    """

    def __init__(self, iou_thr=0.3, max_age=30):
        self.iou_thr = iou_thr
        self.max_age = max_age
        self.next_id = 1
        self.tracks = []  # {id, bbox, age}

    def update(self, detections):
        for t in self.tracks:
            t["age"] += 1
        out = []
        used = set()
        for det in detections:
            best, best_iou = None, self.iou_thr
            for t in self.tracks:
                if t["id"] in used:
                    continue
                i = _iou(t["bbox"], det)
                if i > best_iou:
                    best, best_iou = t, i
            if best is None:
                best = {"id": self.next_id, "bbox": det[:4], "age": 0}
                self.next_id += 1
                self.tracks.append(best)
            else:
                best["bbox"] = det[:4]
                best["age"] = 0
            used.add(best["id"])
            x1, y1, x2, y2 = det[:4]
            out.append({"id": best["id"], "cx": (x1 + x2) / 2, "cy": (y1 + y2) / 2})
        self.tracks = [t for t in self.tracks if t["age"] <= self.max_age]
        return out


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
        self.detector = Detector(conf)
        self.tracker = Tracker()
        self.seen_tracks: dict = {}  # track_id -> {enter_ts, counted}

    def run(self):
        if not self.conf.rtsp_sub:
            print(f"[{self.name}] RTSP manzil yo'q — kutish rejimi.")
            self.stop.wait(3600)
            return
        try:
            import cv2  # type: ignore
        except Exception:  # noqa: BLE001
            print(f"[{self.name}] OpenCV o'rnatilmagan (pip install opencv-python-headless).")
            self.stop.wait(3600)
            return
        interval = 1.0 / max(0.5, self.conf.process_fps)
        cap = None
        last = 0.0
        while not self.stop.is_set():
            try:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.conf.rtsp_sub)
                    if not cap.isOpened():
                        print(f"[{self.name}] kameraga ulanib bo'lmadi, qayta urinish...")
                        self.stop.wait(5)
                        continue
                    print(f"[{self.name}] kameraga ulandi.")
                ok, frame = cap.read()
                if not ok or frame is None:
                    cap.release()
                    cap = None
                    self.stop.wait(2)
                    continue
                now = time.time()
                if now - last < interval:  # process_fps ga qarab kadrlarни tashlab yuboramiz
                    continue
                last = now
                self._process_frame(frame)
            except NotImplementedError:
                self.stop.wait(2)
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] xato: {e}")
                if cap is not None:
                    cap.release()
                    cap = None
                self.stop.wait(2)
        if cap is not None:
            cap.release()

    def _process_frame(self, frame):
        """Bitta kadr: aniqlash → treklash → zona/dwell → hodisa navbatiga."""
        h, w = frame.shape[:2]
        detections = self.detector.detect(frame)
        tracks = self.tracker.update(detections)
        shop_id = self.conf.shops[0]["id"] if self.conf.shops else None
        alive = set()
        for tr in tracks:
            ncx, ncy = tr["cx"] / max(1, w), tr["cy"] / max(1, h)  # 0..1 normallashtirish
            if self.conf.staff_zone and point_in_zone(ncx, ncy, self.conf.staff_zone):
                continue  # sotuvchi zonasi — sanalmaydi
            if not point_in_zone(ncx, ncy, self.conf.counter_zone):
                continue
            alive.add(tr["id"])
            rec = self.seen_tracks.setdefault(tr["id"], {"enter": time.time(), "counted": False})
            dwell = time.time() - rec["enter"]
            if not rec["counted"] and dwell >= self.conf.min_dwell_seconds:
                rec["counted"] = True
                self.q.put(
                    {
                        "_token": self.conf.token,  # Sender har kamera tokeni bilan yuboradi
                        "type": "visit",
                        "shop_id": shop_id,
                        "timestamp": now_iso(),
                        "payload": {"dwell_seconds": int(dwell), "track_id": str(tr["id"])},
                    }
                )
        # Zonadan chiqib ketgan tracklarni unutamiz (xotira o'smasin)
        for tid in list(self.seen_tracks):
            if tid not in alive:
                self.seen_tracks.pop(tid, None)


# ============================================================================
#  Yuboruvchi (batch) va heartbeat
# ============================================================================
class Sender(threading.Thread):
    def __init__(self, conf: WorkerConf, default_token: str, q: queue.Queue, stop: threading.Event):
        super().__init__(daemon=True, name="sender")
        self.conf = conf
        self.q = q
        self.stop = stop
        self.default_token = default_token

    def run(self):
        while not self.stop.is_set():
            time.sleep(self.conf.batch_seconds)
            batch = []
            while not self.q.empty() and len(batch) < 200:
                batch.append(self.q.get())
            if not batch:
                continue
            # Har kamera o'z tokeni bilan yuboriladi (hodisa qaysi kameradan — o'sha token)
            by_token: dict = {}
            for ev in batch:
                tok = ev.pop("_token", None) or self.default_token
                by_token.setdefault(tok, []).append(ev)
            for tok, events in by_token.items():
                self._post(tok, events)

    def _post(self, token, events):
        if requests is None:
            print("requests o'rnatilmagan — yuborilmadi:", len(events))
            return
        try:
            r = requests.post(
                f"{self.conf.backend_url}/api/events/",
                json={"events": events},
                headers={"X-Camera-Token": token},
                timeout=8,
            )
            if r.status_code >= 300:
                print("Backend xatosi:", r.status_code, r.text[:120])
        except requests.RequestException as e:
            print("Yuborishда xato (navbatda saqlanadi):", e)
            for ev in events:  # keyingi urinishga qaytaramiz (token bilan)
                ev["_token"] = token
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
                    requests.post(
                        f"{self.conf.backend_url}/api/cameras/heartbeat/",
                        headers={"X-Camera-Token": cam.token},
                        timeout=5,
                    )
                except requests.RequestException:
                    pass
            self.stop.wait(self.conf.heartbeat_seconds)


def fetch_remote_config(conf: WorkerConf):
    """Har kamera uchun backend'dan zonalar/do'konlarni oladi."""
    if requests is None:
        return
    for cam in conf.cameras:
        try:
            r = requests.get(
                f"{conf.backend_url}/api/cameras/config/",
                headers={"X-Camera-Token": cam.token},
                timeout=8,
            )
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
    default_token = conf.cameras[0].token if conf.cameras else ""

    threads = [Sender(conf, default_token, q, stop), Heartbeat(conf, stop)]
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
