"""Yuklama testi — N ta parallel foydalanuvchi, javob vaqtlari (p50/p95/p99), xatolar ulushi.

    python manage.py loadtest --url http://127.0.0.1:8000 --login nazorat --password ... \\
        --users 20 --duration 60
    python manage.py loadtest --url https://staging... --role seller --login ... --write

Standart holatda FAQAT o'qiydi (GET) — ishlab turgan tizimga zarar yo'q. --write sotuv ham
yaratadi (API orqali) — faqat sinov (staging) serverida ishlating!
Bitta sessiya (bitta login) barcha oqimlarga ulashiladi — audit jurnali to'lib ketmaydi.
SLO: p95 < 800 ms, xatolar < 1% (davlat tizimi uchun bozor kuni cho'qqisida).
"""

from __future__ import annotations

import http.cookiejar
import json
import random
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

SCENARIOS = {
    "inspector": ["/", "/xarita/", "/signallar/", "/statistika/", "/tekshiruvlar/", "/ombor/"],
    "seller": ["/", "/sotuv/", "/mahsulotlar/", "/hisobot/", "/api/sales/today/",
               "/api/products/lookup/?q=a"],
    "panel": ["/", "/foydalanuvchilar/", "/bozorlar/"],
    "public": ["/healthz/", "/login/"],
}
SLO_P95_MS = 800
SLO_ERR_PCT = 1.0


def _pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round(p / 100 * (len(values) - 1)))))
    return values[k]


class Command(BaseCommand):
    help = "Yuklama testi: parallel foydalanuvchilar, p50/p95/p99, xatolar ulushi."

    def add_arguments(self, parser):
        parser.add_argument("--url", default="http://127.0.0.1:8000")
        parser.add_argument("--role", choices=list(SCENARIOS), default="inspector")
        parser.add_argument("--login", default="")
        parser.add_argument("--password", default="")
        parser.add_argument("--users", type=int, default=10)
        parser.add_argument("--duration", type=int, default=30, help="soniya")
        parser.add_argument("--think", type=float, default=0.5, help="so'rovlar orasida pauza, s")
        parser.add_argument("--write", action="store_true", help="sotuv ham yaratish (staging!)")

    def _opener(self, base, login, password):
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        opener.addheaders = [("User-Agent", "BozorNazorat-loadtest/1.0")]
        if not login:
            return opener, ""
        opener.open(f"{base}/login/", timeout=15).read()
        csrf = next((c.value for c in jar if c.name == "csrftoken"), "")
        data = urllib.parse.urlencode({"username": login, "password": password,
                                       "csrfmiddlewaretoken": csrf}).encode()
        req = urllib.request.Request(f"{base}/login/", data=data,
                                     headers={"Referer": f"{base}/login/"})
        resp = opener.open(req, timeout=15)
        resp.read()
        if "sessionid" not in {c.name for c in jar}:
            raise CommandError("Login bo'lmadi (parol, blok yoki 2FA yoqilgan hisob).")
        csrf = next((c.value for c in jar if c.name == "csrftoken"), csrf)
        return opener, csrf

    def handle(self, *args, **o):
        base = o["url"].rstrip("/")
        role = o["role"]
        if role != "public" and not o["login"]:
            raise CommandError("--login va --password kerak (yoki --role public).")
        if o["write"] and role != "seller":
            raise CommandError("--write faqat --role seller bilan.")
        opener, csrf = self._opener(base, o["login"], o["password"])
        paths = SCENARIOS[role]
        stats = defaultdict(list)
        errors = defaultdict(int)
        lock = threading.Lock()
        stop_at = time.monotonic() + o["duration"]

        def one(method, path, body=None):
            headers = {"Referer": base + "/"}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers.update({"Content-Type": "application/json", "X-CSRFToken": csrf})
            req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
            t = time.perf_counter()
            ok = True
            try:
                with opener.open(req, timeout=30) as resp:
                    resp.read()
                    ok = resp.status < 400
            except urllib.error.HTTPError as e:
                ok = e.code < 400
            except (urllib.error.URLError, TimeoutError, OSError):
                ok = False
            ms = (time.perf_counter() - t) * 1000
            key = f"{method} {path.split('?')[0]}"
            with lock:
                stats[key].append(ms)
                if not ok:
                    errors[key] += 1

        def worker(n):
            rnd = random.Random(n)
            time.sleep(rnd.random() * min(2.0, o["think"] * 2))  # birdaniga emas
            while time.monotonic() < stop_at:
                if o["write"] and rnd.random() < 0.3:
                    amount = rnd.choice([5000, 12000, 25000, 40000])
                    one("POST", "/api/sales/", {"items": [{"name": "Yuklama testi", "qty": 1,
                                                           "unit_price": amount}],
                                                "payment_type": "cash", "note": "loadtest"})
                else:
                    one("GET", rnd.choice(paths))
                time.sleep(rnd.uniform(0, o["think"] * 2))

        self.stdout.write(f"{o['users']} foydalanuvchi × {o['duration']} s → {base} ({role})"
                          + (" + SOTUV YOZISH" if o["write"] else " — faqat o'qish"))
        threads = [threading.Thread(target=worker, args=(i,), daemon=True)
                   for i in range(o["users"])]
        started = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(o["duration"] + 60)
        elapsed = time.monotonic() - started

        all_ms = [v for vals in stats.values() for v in vals]
        total, total_err = len(all_ms), sum(errors.values())
        title = "So'rov"
        self.stdout.write(f"\n{title:34} {'soni':>6} {'xato':>5} {'p50':>7} {'p95':>7} {'p99':>7}")
        for key in sorted(stats):
            v = stats[key]
            self.stdout.write(f"{key:34} {len(v):6} {errors[key]:5} {_pct(v, 50):6.0f}ms "
                              f"{_pct(v, 95):6.0f}ms {_pct(v, 99):6.0f}ms")
        if not total:
            raise CommandError("Birorta ham so'rov bajarilmadi.")
        p95 = _pct(all_ms, 95)
        err_pct = total_err / total * 100
        self.stdout.write(
            f"\nJami: {total} so'rov, {total / elapsed:.1f} so'rov/s, xato {err_pct:.2f}%, "
            f"o'rtacha {statistics.mean(all_ms):.0f} ms, p95 {p95:.0f} ms, p99 {_pct(all_ms, 99):.0f} ms"
        )
        ok = p95 < SLO_P95_MS and err_pct < SLO_ERR_PCT
        verdict = (f"SLO bajarildi (p95 < {SLO_P95_MS} ms, xato < {SLO_ERR_PCT}%)" if ok
                   else f"SLO BAJARILMADI (p95 < {SLO_P95_MS} ms, xato < {SLO_ERR_PCT}% talab)")
        self.stdout.write((self.style.SUCCESS if ok else self.style.ERROR)(verdict))
